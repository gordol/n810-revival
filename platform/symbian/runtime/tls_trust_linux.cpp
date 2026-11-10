// Native trust validation for the standalone Linux frontend; no Qt dependency.
#include <cstdint>
#include <string>
#include <vector>
#include <mbedtls/x509_crt.h>
namespace eka2l1::drivers {
bool verify_system_certificate(const std::vector<std::vector<std::uint8_t>> &chain,const std::string &hostname) {
    if (chain.empty() || chain.size()>16 || hostname.empty()) return false;
    mbedtls_x509_crt leaf,roots;
    mbedtls_x509_crt_init(&leaf);mbedtls_x509_crt_init(&roots);
    bool good=true;
    for (const auto &der:chain) {
        if (der.empty() || der.size()>1024*1024 || mbedtls_x509_crt_parse_der(&leaf,der.data(),der.size())!=0) {good=false;break;}
    }
    if (good) good=mbedtls_x509_crt_parse_file(&roots,"/etc/ssl/certs/ca-certificates.crt")>=0;
    std::uint32_t flags=0;
    if (good) good=mbedtls_x509_crt_verify(&leaf,&roots,nullptr,hostname.c_str(),&flags,nullptr,nullptr)==0 && flags==0;
    mbedtls_x509_crt_free(&roots);mbedtls_x509_crt_free(&leaf);
    return good;
}
}
