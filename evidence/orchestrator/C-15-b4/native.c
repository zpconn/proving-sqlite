#include "sqlite3.c"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned state = 0xC150004u;
static unsigned rnd(void){ state ^= state<<13; state ^= state>>17; state ^= state<<5; return state; }
static unsigned cases, beyond;
static int range(size_t b, size_t o, size_t n){ return b>=o && b-o<n; }
static int written(size_t b){
  return range(b,offsetof(Mem,u),sizeof(((Mem*)0)->u))
    || range(b,offsetof(Mem,z),sizeof(((Mem*)0)->z))
    || range(b,offsetof(Mem,n),sizeof(((Mem*)0)->n))
    || range(b,offsetof(Mem,flags),sizeof(((Mem*)0)->flags))
    || range(b,offsetof(Mem,enc),sizeof(((Mem*)0)->enc))
    || range(b,offsetof(Mem,db),sizeof(((Mem*)0)->db))
    || range(b,offsetof(Mem,szMalloc),sizeof(((Mem*)0)->szMalloc));
}
static void check(unsigned cap,int nKey,unsigned char *buf){
  KeyInfo key = {0};
  key.nKeyField=cap-1; key.enc=SQLITE_UTF8;
  UnpackedRecord *p=sqlite3VdbeAllocUnpackedRecord(&key);
  if(!p) abort();
  unsigned char rec[sizeof(UnpackedRecord)];
  size_t len=sizeof(Mem)*cap;
  unsigned char *old=malloc(len);
  if(!old) abort();
  for(size_t i=0;i<len;i++) ((unsigned char *)p->aMem)[i]=rnd();
  memcpy(old,p->aMem,len); memcpy(rec,p,sizeof(rec));
  sqlite3VdbeRecordUnpack(nKey,buf,p);
  if(p->nField>cap || p->default_rc!=0) abort();
  for(size_t i=0;i<sizeof(rec);i++)
    if(!range(i,offsetof(UnpackedRecord,nField),sizeof(p->nField))
       && !range(i,offsetof(UnpackedRecord,default_rc),sizeof(p->default_rc))
       && rec[i]!=((unsigned char *)p)[i]) abort();
  for(size_t i=0;i<len;i++)
    if(!written(i%sizeof(Mem)) && old[i]!=((unsigned char *)p->aMem)[i]) abort();
  cases++; beyond+=(cap>4 || nKey>256);
  free(old); sqlite3DbFree(0,p);
}
static void random_case(unsigned cap,int n,int mode){
  size_t size=(size_t)(n>0?n:1)+8;
  unsigned char *b=malloc(size);
  if(!b) abort();
  for(size_t i=0;i<size;i++) b[i]=rnd();
  if(mode==1) memset(b,0xff,size);
  if(mode==2) memset(b,0,size);
  /* A short header followed by an eight-byte integer, possibly past nKey. */
  if(mode==3){ b[0]=2; b[1]=6; }
  /* Long header ending at nKey: the last serial value needs all eight slack bytes. */
  if(mode==4 && n>=2){ unsigned h=sqlite3PutVarint(b,(u64)n); if(h<(unsigned)n)b[h]=6; }
  check(cap,n,b); free(b);
}
static void valid_case(unsigned cap){
  unsigned hdr=cap+1;
  unsigned char varint[9];
  while(hdr != cap+(unsigned)sqlite3PutVarint(varint,hdr)) hdr=cap+sqlite3PutVarint(varint,hdr);
  unsigned payload=0;
  for(unsigned i=0;i<cap;i++) payload+=sqlite3VdbeSerialTypeLen(i%14);
  unsigned n=hdr+payload;
  unsigned char *b=malloc((size_t)n+8);
  if(!b)abort();
  for(size_t i=0;i<(size_t)n+8;i++)b[i]=rnd();
  unsigned p=sqlite3PutVarint(b,hdr);
  for(unsigned i=0;i<cap;i++) b[p+i]=i%14;
  check(cap,n,b);free(b);
}
int main(int argc,char **argv){
  if(sqlite3_initialize()!=SQLITE_OK)return 1;
  if(argc>1){
    int n=atoi(argv[1]);
    size_t size=(size_t)(n>0?n:1)+7;
    unsigned char *b=malloc(size);
    memset(b,0x80,size);
    if(n==2){ b[0]=2; b[1]=6; }
    check(1,n,b); free(b);
    puts("RESULT native-minus-one unexpectedly survived");
    return 1;
  }
  unsigned caps[]={1,4,5,8,16,32,255,256,65535};
  int ns[]={0,1,2,255,256,257,1024,4096,65536};
  for(unsigned c=0;c<sizeof(caps)/sizeof(*caps);c++){
    valid_case(caps[c]);
    for(unsigned j=0;j<sizeof(ns)/sizeof(*ns);j++)
      for(unsigned mode=0;mode<5;mode++) random_case(caps[c],ns[j],mode);
  }
  for(unsigned i=0;i<1000;i++)random_case(5+rnd()%60,257+rnd()%8192,0);
  printf("RESULT native PASS %u cases, %u beyond proposed bounds; seed 0xC150004\n",cases,beyond);
  sqlite3_shutdown();
}
