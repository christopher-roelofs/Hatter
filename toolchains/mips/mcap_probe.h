/* Minimal declarations for the C probe; selectors come from the SDK .cdef
 * files via the stub generator, not from this header. */
typedef unsigned int Reference;
typedef unsigned char Boolean;
#define Method
Reference Name(Reference self);
void SetName(Reference self, Reference name);
void Honk(void);
