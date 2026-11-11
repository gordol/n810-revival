#include "host_graphics_profile.h"
#include <drivers/audio/audio.h>
// N810-only frontend for the upstream EKA2 process and service runtime.
// Firmware, installed applications and mutable C/E drives are private inputs.
#include "graphics_session.h"
#include "keyboard_input.h"
#include "input_wakeup.h"
#include "fault_capture.h"
#include "runtime_diagnostics.h"
#include "n95_cdl_compat.h"
#include "native_fast_exec.h"
#include "native_cpu_profile.h"
#include "native_trampoline.h"
#include <services/window/window.h>
#include <services/applist/applist.h>
#include <utils/apacmd.h>
#include <vfs/vfs.h>
#include <system/epoc.h>
#include <system/devices.h>
#include <config/config.h>
#include <config/app_settings.h>
#include <common/cvt.h>
#include <common/log.h>
#include <cpu/arm_interface.h>
#include <kernel/kernel.h>
#include <kernel/process.h>
#include <sys/resource.h>
#include <unistd.h>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <filesystem>
#include <malloc.h>

namespace n810_runtime {void drain_frontend_callbacks();}
namespace eka2l1::drivers {void report_sync_command_timing();}
extern "C" bool n810_frontend_event_input_ready(){return n810_event_input_active.load(std::memory_order_acquire);}
static volatile std::sig_atomic_t interrupted = 0;
static void stop(int) { interrupted = 1;n810_runtime::interrupt_window();n810_wake_runtime(); }

static void trace_host_heap() {
    if(!std::getenv("N810_SYMBIAN_TRACE_ATLAS"))return;
    const auto heap=mallinfo2();
    std::printf("host_heap arena_bytes=%zu allocated_bytes=%zu free_bytes=%zu mmap_bytes=%zu\n",
        heap.arena,heap.uordblks,heap.fordblks,heap.hblkhd);
}
static int run(int argc, char **argv) {
    // This frontend executes guest ARM on the N810 CPU. Never silently select
    // the upstream interpreter/recompiler when a launcher omits its setting.
    const char *cpu_backend=std::getenv("N810_SYMBIAN_CPU");
    if(cpu_backend&&std::strcmp(cpu_backend,"native"))
        throw std::runtime_error("N810 runtime requires native ARM execution");
    setenv("N810_SYMBIAN_CPU","native",1);
    eka2l1::arm::reserve_native_trampoline();
    n810_fault::install();
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    const auto start = std::chrono::steady_clock::now();
    const auto phase=[&](const char *name) {
        std::printf("runtime_phase=%s elapsed_ms=%.3f\n",name,
            std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
    };
    if (argc != 4 && argc != 5) {
        std::fprintf(stderr, "usage: symbian-runtime PRIVATE_ROOT GUEST_EXE SECONDS [PRIVATE_SIS]\n");
        return 2;
    }
    const auto root = std::filesystem::canonical(argv[1]);
    const int seconds = std::stoi(argv[3]);
    if (seconds < 1 || seconds > 900 || !std::filesystem::exists(root / "data/devices.yml")) {
        std::fprintf(stderr, "invalid private runtime root or bounded duration\n");
        return 2;
    }
    // Framebuffer access is optional and inherited from a separate desktop-restoration supervisor.
    std::filesystem::current_path(root);
    eka2l1::log::setup_log(nullptr);
    if (eka2l1::log::filterings) eka2l1::log::filterings->parse_filter_string("*:warn");
    // Import tracing is opt-in; never force it in normal execution.
    setenv("GALLIUM_DRIVER", "softpipe", 1);
    const char *fb_env=std::getenv("N810_SYMBIAN_FB_FD");
    std::signal(SIGINT, stop);
    std::signal(SIGTERM, stop);
    phase("graphics_create");
    graphics_session graphics(fb_env ? std::stoi(fb_env) : -1);
    phase("graphics_ready");
    if(interrupted)return 130;
    rlimit cpu_limit{static_cast<rlim_t>(seconds + 10), static_cast<rlim_t>(seconds + 15)};
    setrlimit(RLIMIT_CPU, &cpu_limit);
    eka2l1::config::state conf;
    conf.storage = "data";
    conf.cpu_backend = "12l1r";
    eka2l1::config::app_settings settings(&conf);
    eka2l1::system_create_components components;
    components.conf_ = &conf;
    components.settings_ = &settings;
    components.graphics_ = graphics.driver();
    // Audio stays disabled until the physical McBSP path is accepted. This is
    // absence of a device, not a fake successful PCM sink or timed callbacks.
    std::unique_ptr<eka2l1::drivers::audio_driver> audio;
    const char *audio_backend=std::getenv("N810_SYMBIAN_AUDIO");
    if(audio_backend&&std::strcmp(audio_backend,"none")) {
        if(std::strcmp(audio_backend,"alsa"))throw std::runtime_error("Unsupported N810 audio backend");
        audio=eka2l1::drivers::make_audio_driver(eka2l1::drivers::audio_driver_backend::cubeb,25);
        if(!audio||!audio->native_sample_rate())throw std::runtime_error("Native ALSA audio initialization failed");
        std::printf("audio_backend=cubeb_alsa native_rate=%u master_volume=25\n",audio->native_sample_rate());
    } else std::printf("audio_backend=disabled pcm_callbacks=0\n");
    components.audio_ = audio.get();
    components.cache_root_ = "cache";
    eka2l1::system runtime(components);
    phase("system_created");
    runtime.set_cpu_executor_type(arm_emulator_type::r12l1);
    std::printf("cpu_backend=native direct_arm=1 interpreter=0 jit=0\n");
    runtime.startup();
    n810_fault::cpu=runtime.get_cpu();
    phase("startup_complete");
    if (!runtime.get_device_manager()->total() || !runtime.set_device(0)) {
        std::fprintf(stderr, "N95 runtime initialization failed\n");
        return 3;
    }
    runtime.mount_device_drives();
    // ROM loading creates the ROM filesystem; mounting Z afterward lets WSERV
    // and the E32 loader resolve the N95 resources and imported system DLLs.
    runtime.mount(drive_z,drive_media::rom,"data/drives/z/",
        io_attrib_internal | io_attrib_write_protected);
    phase("device_mounted");
    apply_n95_cdl_cancel_compat(runtime.get_memory_system(),runtime.get_cpu());
    apply_native_fast_exec(runtime.get_memory_system(),runtime.get_cpu());
    if (argc == 5) {
        auto package=std::filesystem::canonical(argv[4]);
        auto relative=package.lexically_relative(root);
        if (relative.empty() || *relative.begin()=="..") throw std::runtime_error("Installer must be inside private runtime root");
        const int installed=runtime.install_package(eka2l1::common::utf8_to_ucs2(package.string()),drive_c);
        std::printf("sis_install_status=%d\n",installed);std::fflush(stdout);
        if (installed!=0) return 6;
    }
    runtime.initialize_user_parties();
    // Match upstream's S60v3 FP1 input-method replacement. Modify only this
    // private extracted Z drive, retaining its original DLL; never SYM.rom.
    if (runtime.get_symbian_version_use() >= epocver::epoc93fp1) {
        auto raw=runtime.get_io_system()->get_raw_path(u"Z:\\sys\\bin\\avkonfep.dll");
        if (!raw) throw std::runtime_error("N95 input-method path missing");
        auto destination=std::filesystem::weakly_canonical(eka2l1::common::ucs2_to_utf8(*raw));
        auto relative=destination.lexically_relative(root);
        if (relative.empty() || *relative.begin()=="..") throw std::runtime_error("Input-method destination outside private root");
        auto source=root/"patch/avkonfep_general.dll";
        auto backup=destination;backup+=".symbian-original";
        if (!std::filesystem::exists(backup)) std::filesystem::copy_file(destination,backup);
        auto temporary=destination;temporary+=".n810-next";
        std::filesystem::copy_file(source,temporary,std::filesystem::copy_options::overwrite_existing);
        std::filesystem::rename(temporary,destination);
        std::printf("private_runtime_patch=avkonfep original_preserved=1\n");
    }
    phase("user_services_initialized");
    auto *server=reinterpret_cast<eka2l1::window_server *>(runtime.get_kernel_system()->get_by_name<eka2l1::service::server>(
        eka2l1::get_winserv_name_by_epocver(runtime.get_symbian_version_use())));
    if (!server || !server->get_screen(0)) return 4;
    auto *screen=server->get_screen(0);
    const auto callback=screen->add_screen_redraw_callback(&graphics,[](void *opaque,eka2l1::epoc::screen *s,bool) {
        static_cast<graphics_session *>(opaque)->redraw(s);
    });
    // GUI applications need AppArc's registered launch path, including its
    // application stack sizing and process logon, not the bare EXE loader.
    auto *kernel=runtime.get_kernel_system();
    n810_runtime_wakeup signal_wakeup([kernel]{kernel->stop_cores_idling();});
    runtime_diagnostics diagnostics(kernel);
    // Real Symbian boots ECom before GUI applications. Starting it on demand
    // inside CDL construction can exhaust CDL's shutdown timer on a slow host.
    // Wait for the actual guest RProcess::Rendezvous, not a fabricated status or
    // an arbitrary delay; the guest process and its native server remain alive.
    auto *ecom=kernel->spawn_new_process(u"Z:\\sys\\bin\\ecomserver.exe");
    if(!ecom)throw std::runtime_error("Cannot load private N95 ECom startup service");
    ecom->increase_access_count();
    auto release_ecom=[](eka2l1::kernel::process *process){process->decrease_access_count();};
    std::unique_ptr<eka2l1::kernel::process,decltype(release_ecom)> ecom_hold(ecom,release_ecom);
    bool ecom_ready=false;int ecom_result=0;
    const auto ecom_callback=ecom->register_rendezvous_callback([&](eka2l1::kernel::process *,std::int32_t reason) {
        ecom_result=reason;ecom_ready=true;
    });
    if(!ecom->run())throw std::runtime_error("Cannot start ECom guest service");
    auto boot_progress=std::chrono::steady_clock::now();
    while(!interrupted && !ecom_ready && !runtime.should_exit() &&
          ecom->get_exit_type()==eka2l1::kernel::entity_exit_type::pending &&
          std::chrono::steady_clock::now()-start<std::chrono::seconds(seconds)) {
        runtime.loop();
        if(std::chrono::steady_clock::now()-boot_progress>std::chrono::seconds(5)) {
            phase("ecom_boot_progress");diagnostics.dump();
            native_profile::poll();boot_progress=std::chrono::steady_clock::now();
        }
    }
    ecom->unregister_rendezvous_callback(ecom_callback);
    if(!ecom_ready || ecom_result!=0)throw std::runtime_error("ECom guest startup did not rendezvous successfully");
    phase("ecom_rendezvous_complete");
    auto *applist=reinterpret_cast<eka2l1::applist_server *>(kernel->get_by_name<eka2l1::service::server>(
        eka2l1::get_app_list_server_name_by_epocver(runtime.get_symbian_version_use())));
    if (!applist) throw std::runtime_error("Application registry unavailable");
    // Reuse AppArc's resolved names and paths; publish only installed user apps.
    if (FILE *catalog=std::fopen("apps.tsv.next","w")) {
        for (auto &reg : applist->get_registerations()) {
            if (reg.caps.is_hidden || reg.land_drive == drive_z) continue;
            auto path=eka2l1::common::ucs2_to_utf8(reg.mandatory_info.app_path.to_std_string(nullptr));
            auto title=eka2l1::common::ucs2_to_utf8(reg.mandatory_info.long_caption.to_std_string(nullptr));
            if(path.find_first_of("\t\r\n")!=std::string::npos)continue;
            for(char &c:title)if(c=='\t'||c=='\r'||c=='\n')c=' ';
            std::fprintf(catalog,"%08x\t%s\t%s\n",reg.mandatory_info.uid,path.c_str(),title.c_str());
        }
        if(std::fclose(catalog)==0)std::filesystem::rename("apps.tsv.next","apps.tsv");
    }
    if (std::strcmp(argv[2],"--catalog")==0) return 0;
    auto guest_file=runtime.get_io_system()->open_file(eka2l1::common::utf8_to_ucs2(argv[2]),READ_MODE|BIN_MODE);
    std::uint32_t app_uid=0;
    if (!applist || !guest_file || guest_file->read_file(8,&app_uid,1,4)!=4) throw std::runtime_error("Cannot read application UID");
    auto *registration=applist->get_registration(app_uid);
    if (!registration) throw std::runtime_error("Installed application registration missing");
    std::printf("apparc_registration uid=%08x guest_exe=%s\n",app_uid,argv[2]);
    eka2l1::epoc::apa::command_line command;
    eka2l1::kernel::uid thread_id=0;
    auto app_exited=std::make_shared<std::atomic<bool>>(false);
    auto app_failed=std::make_shared<std::atomic<bool>>(false);
    if (!applist->launch_app(*registration,command,&thread_id,[app_exited,app_failed,kernel](eka2l1::kernel::process *process) {
        std::printf("guest_app_exit name=%s type=%d category=%s reason=%d\n",process->name().c_str(),
            static_cast<int>(process->get_exit_type()),eka2l1::common::ucs2_to_utf8(process->get_exit_category()).c_str(),process->get_exit_reason());
        *app_failed=process->get_exit_reason()!=0 || process->get_exit_type()==eka2l1::kernel::entity_exit_type::panic;
        *app_exited=true;kernel->stop_cores_idling();
    })) {
        std::fprintf(stderr, "AppArc process/import loading failed\n");
        return 5;
    }
    std::printf("apparc_thread=%llu\n",static_cast<unsigned long long>(thread_id));
    std::printf("process_loaded_ms=%.3f\n",std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
    std::fflush(stdout);
    native_profile::begin();
    host_graphics_profile::sampler runtime_sampler("runtime");
    std::unique_ptr<n810_input_wakeup> input_wakeup;
    std::size_t slices = 0;
    auto last_progress=std::chrono::steady_clock::now();
    const bool input_timing=std::getenv("N810_SYMBIAN_INPUT_TIMING")!=nullptr;
    auto last_input_poll=last_progress;
    long long max_loop_us=0,max_input_poll_gap_us=0;
    while (!interrupted && !app_exited->load() && !graphics.failed() && !runtime.should_exit() &&
           std::chrono::steady_clock::now() - start < std::chrono::seconds(seconds)) {
        const auto loop_started=input_timing?std::chrono::steady_clock::now():last_input_poll;
        runtime_sampler.poll();
        runtime.loop();
        if(input_timing){
            const auto now=std::chrono::steady_clock::now();
            const auto loop_us=std::chrono::duration_cast<std::chrono::microseconds>(now-loop_started).count();
            const auto gap_us=std::chrono::duration_cast<std::chrono::microseconds>(now-last_input_poll).count();
            if(loop_us>max_loop_us)max_loop_us=loop_us;
            if(gap_us>max_input_poll_gap_us)max_input_poll_gap_us=gap_us;
            last_input_poll=now;
        }
        if (graphics.displayed.load()) {
            if(!input_wakeup) input_wakeup=std::make_unique<n810_input_wakeup>(n810_keyboard_fd(),n810_control_source().fd(),[kernel]{kernel->stop_cores_idling();});
            if(!input_wakeup->active() || input_wakeup->pending()) {drain_n810_inputs(server);input_wakeup->acknowledge();}
        }
        n810_runtime::drain_frontend_callbacks();
        ++slices;
        if (n810_runtime_debug() && std::chrono::steady_clock::now()-last_progress>std::chrono::seconds(5)) {
            rusage progress_usage{};getrusage(RUSAGE_SELF,&progress_usage);
            std::printf("guest_progress slices=%zu pc=%08x cpsr=%08x frames=%lu elapsed_ms=%.0f user_cpu_s=%.3f system_cpu_s=%.3f major_faults=%ld\n",slices,runtime.get_cpu()->get_pc(),runtime.get_cpu()->get_cpsr(),graphics.frames.load(),
                std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count(),
                progress_usage.ru_utime.tv_sec+progress_usage.ru_utime.tv_usec/1e6,
                progress_usage.ru_stime.tv_sec+progress_usage.ru_stime.tv_usec/1e6,progress_usage.ru_majflt);
            if(input_timing){
                eka2l1::drivers::report_sync_command_timing();
                rusage thread_usage{};getrusage(RUSAGE_THREAD,&thread_usage);
                std::printf("input_dispatch max_runtime_loop_us=%lld max_poll_gap_us=%lld thread_user_s=%.6f thread_system_s=%.6f\n",max_loop_us,max_input_poll_gap_us,
                    thread_usage.ru_utime.tv_sec+thread_usage.ru_utime.tv_usec/1e6,
                    thread_usage.ru_stime.tv_sec+thread_usage.ru_stime.tv_usec/1e6);
                max_loop_us=max_input_poll_gap_us=0;
            }
            diagnostics.dump();
            native_profile::poll();
            trace_host_heap();
            last_progress=std::chrono::steady_clock::now();
        }
    }
    std::fprintf(stderr,"runtime_exit interrupted=%d app_exited=%d app_failed=%d graphics_failed=%d system_exit=%d elapsed_ms=%.0f\n",
        int(interrupted),int(app_exited->load()),int(app_failed->load()),int(graphics.failed()),int(runtime.should_exit()),
        std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
    std::fflush(stdout);
    native_profile::poll(true);
    if(input_wakeup)input_wakeup->stop();
    screen->remove_screen_redraw_callback(callback);
    runtime.request_exit();
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    std::printf("runtime_slices=%zu peak_rss_kib=%ld user_cpu_s=%.6f system_cpu_s=%.6f\n", slices,
        usage.ru_maxrss, usage.ru_utime.tv_sec + usage.ru_utime.tv_usec / 1e6,
        usage.ru_stime.tv_sec + usage.ru_stime.tv_usec / 1e6);
    return interrupted ? 130 : app_failed->load() ? 11 : graphics.failed() ? 12 : 0;
}

int main(int argc,char **argv) {
    try {return run(argc,argv);}
    catch (const std::exception &e) {std::fprintf(stderr,"runtime failure: %s\n",e.what());return 10;}
}
