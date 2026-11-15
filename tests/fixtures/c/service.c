#include <string.h>
#include "service.h"

struct user { char name[16]; };

char *find_user(const char *name) {
    static struct user found;
    strcpy(found.name, name);
    return found.name;
}
