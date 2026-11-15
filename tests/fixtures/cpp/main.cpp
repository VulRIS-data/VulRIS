#include <cstdlib>
#include "service.hpp"

int main() {
    UserService service;
    std::system("echo start");
    return service.find("x").size();
}
