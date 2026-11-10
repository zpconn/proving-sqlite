long long conv(double r){ return (long long)r; }
int f2(float r){ return (int)r; }
void exact_min(void){ conv(-0x1p63); }            /* defined: INT64_MIN */
void below_min(void){ conv(-0x1.0000000000001p63); } /* next double below: UB */
void top(void){ conv(0x1.fffffffffffffp62); }      /* largest below 2^63: defined */
void at_top(void){ conv(0x1p63); }                 /* UB */
void f_exact_min(void){ f2(-0x1p31f); }            /* float->int32 exact min: defined */
void i32_exact_min(void){ (void)(int)(-0x1p31); }  /* double->int32 exact min: defined */
