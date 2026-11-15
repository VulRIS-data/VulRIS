package main

import (
	"github.com/gin-gonic/gin"

	"example.com/demo/internal/service"
)

func AuthRequired() gin.HandlerFunc { return func(c *gin.Context) { c.Next() } }

func main() {
	r := gin.Default()
	r.GET("/users/:id", AuthRequired(), func(c *gin.Context) {
		users := &service.UserService{}
		c.String(200, users.Find(c.Param("id")))
	})
	r.Run()
}
