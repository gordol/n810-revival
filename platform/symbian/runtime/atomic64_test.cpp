#include <atomic>
#include <thread>
#include <cstdio>
#include <cstdint>
std::atomic<std::uint64_t> counter{0};
int main() {
 std::uint64_t sums[4]{};std::thread workers[4];
 for(unsigned n=0;n<4;n++)workers[n]=std::thread([&,n]{for(unsigned i=0;i<10000;i++)sums[n]+=counter.fetch_add(1);});
 for(auto &t:workers)t.join();
 std::uint64_t sum=0;for(auto n:sums)sum+=n;
 bool ok=counter.load()==40000 && sum==39999ULL*40000/2;
 ok=ok && counter.fetch_sub(40000)==40000 && counter.load()==0;
 printf("atomic64_contention_pass=%d increments=40000 returned_value_sum=%llu\n",ok,(unsigned long long)sum);return ok?0:1;
}
