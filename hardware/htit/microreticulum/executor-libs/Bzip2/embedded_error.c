/* Required by the upstream BZ_NO_STDIO configuration. No input bytes are logged. */
#include <stdlib.h>
void bz_internal_error(int code) { (void)code; abort(); }
