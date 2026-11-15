#include <stdio.h>
#include "service.h"

int main(int argc, char **argv) {
    char buffer[32];
    gets(buffer);
    printf("%s\n", find_user(buffer));
    return 0;
}
