/* Repro test for campaign.py's fixed build (checkpoint 1, fix 2): the bring-up probe of A-001's premise. */
#include "sqlite3.c"
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
int main(void){
  FILE *f = fopen("/home/zpconn/.gitconfig", "r");
  printf("home readable: %s\n", f ? "yes" : "no");
  int s = socket(AF_INET, SOCK_STREAM, 0);
  struct sockaddr_in a = {0}; a.sin_family = AF_INET; a.sin_port = htons(443); inet_pton(AF_INET, "1.1.1.1", &a.sin_addr);
  printf("network: %s\n", (s >= 0 && connect(s, (struct sockaddr*)&a, sizeof a) == 0) ? "yes" : "no");
  printf("mnt: %s\n", fopen("/mnt/c/Windows/win.ini", "r") ? "visible" : "hidden");
  fflush(stdout);
  KeyInfo ki; memset(&ki, 0, sizeof ki); ki.nKeyField = 1; ki.nAllField = 1; ki.enc = SQLITE_UTF8;
  UnpackedRecord r; Mem m[2]; memset(&r, 0, sizeof r); r.pKeyInfo = &ki; r.aMem = m; r.nField = 2;
  unsigned char *k = malloc(2); k[0] = 0x02; k[1] = 0x81;
  sqlite3VdbeRecordUnpack(2, k, &r);
  printf("returned\n");
  return 0;
}
