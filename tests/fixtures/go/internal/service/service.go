package service

type Base struct{}

func (b *Base) Find(value string) string { return value }

type UserService struct {
	Base
}

func NewUserService() *UserService { return &UserService{} }
