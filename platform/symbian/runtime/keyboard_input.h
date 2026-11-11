#include "input_readiness.h"
#include "runtime_debug.h"
#pragma once
#include <services/window/window.h>
#include <linux/input.h>
#include <unistd.h>
#include <cstdlib>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <stdexcept>
// Consume only the inherited keyboard descriptor while the runtime owns the display.
// No power-button, radio, or touchscreen devices are opened by the runtime.
inline void drain_n810_keyboard(eka2l1::window_server *server) {
    const char *value=std::getenv("N810_SYMBIAN_KEYBOARD_FD");
    if (!value) return;
    const int fd=std::stoi(value);
    input_event input{};
    for (unsigned count=0;count<64;++count) {
        const auto size=read(fd,&input,sizeof(input));
        if (size<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) return;
        if (size!=sizeof(input)) return;
        if (input.type!=EV_KEY || input.value<0 || input.value>2) continue;
        // Symbian WSERV schedules repeats from the physical press/release.
        // Linux repeat events would arm additional timers in that server.
        if (input.value==2) continue;
        using namespace eka2l1::epoc;
        int key=-1;
        switch(input.code) {
        case KEY_UP:key=std_key_up_arrow;break;
        case KEY_DOWN:key=std_key_down_arrow;break;
        case KEY_LEFT:key=std_key_left_arrow;break;
        case KEY_RIGHT:key=std_key_right_arrow;break;
        case KEY_ENTER:case KEY_KPENTER:key=std_key_device_3;break;
        case KEY_MENU:case KEY_F1:key=std_key_device_0;break;
        case KEY_ESC:case KEY_F2:key=std_key_device_1;break;
        case KEY_BACKSPACE:key=std_key_backspace;break;
        case KEY_SPACE:key=std_key_space;break;
        case KEY_0:key='0';break;
        default:if (input.code>=KEY_1 && input.code<=KEY_9) key='1'+input.code-KEY_1;
        }
        if (key<0) continue;
        eka2l1::drivers::input_event event{};
        event.type_=eka2l1::drivers::input_event_type::key_raw;
        event.key_.code_=key;
        event.key_.state_=input.value==0?eka2l1::drivers::key_state::released:
            input.value==2?eka2l1::drivers::key_state::repeat:eka2l1::drivers::key_state::pressed;
        server->queue_input_from_driver(event);
    }
}

// Private, bounded UI-test input. This only feeds this runtime's WSERV after
// display ownership; it never injects keys into Linux or the Pocket desktop.
inline void drain_n810_test_controls(eka2l1::window_server *server) {
    FILE *input=std::fopen("control-keys","r");if(!input)return;
    unlink("control-keys");char name[64];unsigned count=0;
    while(count++<32 && std::fgets(name,sizeof(name),input)) {
        name[std::strcspn(name,"\r\n")]=0;
        using namespace eka2l1::epoc;
        int key=-1;
        if(!std::strcmp(name,"select"))key=std_key_device_3;
        else if(!std::strcmp(name,"left-soft"))key=std_key_device_0;
        else if(!std::strcmp(name,"right-soft"))key=std_key_device_1;
        else if(!std::strcmp(name,"up"))key=std_key_up_arrow;
        else if(!std::strcmp(name,"down"))key=std_key_down_arrow;
        else if(!std::strcmp(name,"left"))key=std_key_left_arrow;
        else if(!std::strcmp(name,"right"))key=std_key_right_arrow;
        if(key<0)continue;
        for(auto state:{eka2l1::drivers::key_state::pressed,eka2l1::drivers::key_state::released}) {
            eka2l1::drivers::input_event event{};event.type_=eka2l1::drivers::input_event_type::key_raw;
            event.key_.code_=key;event.key_.state_=state;server->queue_input_from_driver(event);
        }
        if(n810_runtime_debug()) std::printf("test_key=%s\n",name);
    }
    std::fclose(input);
}

inline n810_control_watch &n810_control_source(){static n810_control_watch control;return control;}
inline int n810_keyboard_fd(){static const int keyboard=[] {const char *p=std::getenv("N810_SYMBIAN_KEYBOARD_FD");return p?std::stoi(p):-1;}();return keyboard;}
inline void drain_n810_inputs(eka2l1::window_server *server) {
 auto &control=n810_control_source();
 const int keyboard=n810_keyboard_fd();
 static bool first=true;
 pollfd fds[2]={{keyboard,POLLIN,0},{control.fd(),POLLIN,0}};
 const int ready=poll(fds,2,0);
 if(ready>0&&(fds[0].revents&POLLIN))drain_n810_keyboard(server);
 if(first||control.fd()<0||(ready>0&&(fds[1].revents&POLLIN))) {
  first=false;if(control.pending())drain_n810_test_controls(server);
 }
}
