/* First native-dispatch probe. Receiver is deliberately unused; no ROM calls,
 * globals or function pointers. A CanGoTo-style Boolean result is 0 or 1. */
unsigned char rosemary_can_go_to(void *receiver)
{
    (void)receiver;
    return 1;
}
