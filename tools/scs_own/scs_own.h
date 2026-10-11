/* scs_own.h - BTicino SCS bus frame -> OpenWebNet message translator (hex -> OWN direction).
 *
 * C port of oracle2/scs_own_all.py (+ scs_own_fw.py for WHO 4), the rules recovered from the
 * mhs1 firmware binaries (bt_luci, coso, bt_termo, bt_supervisione, bt_device, bt_multi) and
 * validated against them.  Pure C99, no allocation, tables in scs_own_tables.h.
 *
 *   uint8_t body[8]; int n = scs_parse_hex("SCS[7]: A8 B8 31 12 00 9B A3", body, 8);  // -> 4 (body bytes)
 *   scs_own_list out; int k = scs_to_own(body, n, &out);                          // -> 1: out.msg[0] = "*1*1*31##"
 */
#ifndef SCS_OWN_H
#define SCS_OWN_H
#include <stdint.h>

#define SCS_OWN_MAX 24          /* max messages one frame can produce (bt_multi frames give up to 22) */
#define SCS_OWN_LEN 96          /* max length of one message */

typedef struct {
    int  n;
    char msg[SCS_OWN_MAX][SCS_OWN_LEN];
} scs_own_list;

/* Parse a text line such as "SCS[7]: A8 B8 31 12 00 9B A3", "A8 .. CHK A3" (also B8/D4 start), "body CHK"
 * or a bare body (any separators). Fills body (4 or 8 bytes, at most max) and returns its length, -1 if none. */
int scs_parse_hex(const char *line, uint8_t *body, int max);

/* Checks the XOR checksum of a full "A8 .. CHK A3" frame text: 1 ok, 0 bad, -1 not framed */
int scs_frame_checksum_ok(const char *line);

/* XOR checksum of a body */
uint8_t scs_xor(const uint8_t *b, int n);

/* Translate a frame body (4 = short, 8 = extended) into OWN messages (deduplicated, firmware order).
 * Bus events come first; a frame that is not a bus event but a request the gateway itself sends
 * (status / dimension requests) is reported as that request. Returns out->n. */
int scs_to_own(const uint8_t *body, int len, scs_own_list *out);

/* Convenience: translate a hex string, join messages with " + " into buf (size bufsz). Returns count. */
int scs_hex_to_own(const char *hex, char *buf, int bufsz);

#endif
