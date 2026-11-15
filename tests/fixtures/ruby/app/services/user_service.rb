class BaseService
  def find(value)
    value
  end
end

class UserService < BaseService
  def find(value)
    normalize(value)
  end

  def normalize(value)
    value.strip
  end
end
