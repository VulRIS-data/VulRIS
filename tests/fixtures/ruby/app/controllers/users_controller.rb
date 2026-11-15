require_relative "../services/user_service"

class UsersController < ApplicationController
  before_action :authenticate_user!

  def show
    users = UserService.new
    render plain: users.find(params[:id])
  end
end
