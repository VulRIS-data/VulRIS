#pragma once
#include <string>

class BaseService {
public:
    virtual ~BaseService() = default;
    virtual std::string find(const std::string &value) { return value; }
};

class UserService : public BaseService {
public:
    std::string find(const std::string &value) override;
};
