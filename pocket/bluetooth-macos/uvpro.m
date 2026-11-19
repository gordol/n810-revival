#import <Foundation/Foundation.h>
#import <IOBluetooth/IOBluetooth.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

@interface Receiver : NSObject <IOBluetoothRFCOMMChannelDelegate>
@property BOOL closed;
@property BOOL queried;
@end
@implementation Receiver
- (void)sdpQueryComplete:(IOBluetoothDevice *)device status:(IOReturn)status { self.queried=YES; }
- (void)rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)channel { self.closed=YES; }
- (void)rfcommChannelData:(IOBluetoothRFCOMMChannel *)channel data:(void *)data length:(size_t)n {
    if (fwrite(data,1,n,stdout)!=n || fflush(stdout)) self.closed=YES;
}
@end
static void spin(void) {
    [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.015]];
}
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc==2 && !strcmp(argv[1],"--power")) {
            IOBluetoothHostController *controller = [IOBluetoothHostController defaultController];
            BluetoothHCIPowerState power = controller ? controller.powerState : kBluetoothHCIPowerStateUnintialized;
            puts(power == kBluetoothHCIPowerStateON ? "on" : power == kBluetoothHCIPowerStateOFF ? "off" : "unknown");
            return 0;
        }
        NSMutableArray *matches=[NSMutableArray array];
        for (IOBluetoothDevice *device in [IOBluetoothDevice pairedDevices]) {
            NSString *name=[device.name.uppercaseString stringByReplacingOccurrencesOfString:@"-" withString:@""];
            if ([name isEqual:@"UVPRO"]) [matches addObject:device];
        }
        if (argc==2 && !strcmp(argv[1],"--count")) { printf("%lu\n",(unsigned long)matches.count);return 0; }
        if (matches.count!=1) { fprintf(stderr,"%s\n",matches.count?"Multiple UV-PROs paired. Select a single paired radio.":"No paired UV-PRO visible. Enable Pairing on the radio and pair it in Mac Bluetooth Settings.");return 1; }
        IOBluetoothDevice *device=matches.firstObject;
        Receiver *receiver=[Receiver new];
        IOBluetoothSDPUUID *uuid=[IOBluetoothSDPUUID uuid16:0x1101];
        IOBluetoothSDPServiceRecord *service=[device getServiceRecordForUUID:uuid];
        if (!service && [device performSDPQuery:receiver]==kIOReturnSuccess) {
            NSDate *end=[NSDate dateWithTimeIntervalSinceNow:10];
            while (!receiver.queried && end.timeIntervalSinceNow>0) spin();
            service=[device getServiceRecordForUUID:uuid];
        }
        BluetoothRFCOMMChannelID cid=0;
        IOBluetoothRFCOMMChannel *channel=nil;
        if (!service || [service getRFCOMMChannelID:&cid]!=kIOReturnSuccess ||
            [device openRFCOMMChannelSync:&channel withChannelID:cid delegate:receiver]!=kIOReturnSuccess) {
            fprintf(stderr,"UV-PRO serial service unavailable. Disconnect other radio clients and retry.\n");return 2;
        }
        printf("READY %s\n",device.addressString.UTF8String);fflush(stdout);
        fcntl(STDIN_FILENO,F_SETFL,O_NONBLOCK);
        unsigned char buffer[1024];
        while (!receiver.closed) { @autoreleasepool {
            spin();
            ssize_t size=read(STDIN_FILENO,buffer,sizeof(buffer));
            if (size==0) break;
            if (size<0) { if(errno==EAGAIN || errno==EINTR)continue;break; }
            size_t offset=0;
            while (offset<(size_t)size) {
                UInt16 count=(UInt16)MIN((size_t)[channel getMTU],size-offset);
                if (!count || [channel writeSync:buffer+offset length:count]!=kIOReturnSuccess){receiver.closed=YES;break;}
                offset+=count;
            }
        }}
        [channel closeChannel];return 0;
    }
}
