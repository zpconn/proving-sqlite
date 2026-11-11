/* Positive control: UBSan's float-cast-overflow flags the next double below -2^63. */
#include <stdio.h>
int main(void){ volatile double r = -0x1.0000000000001p63; long long y = (long long)r; printf("%lld\n", y); return 0; }
