export class BaseService {
  find(value) { return value; }
}

export class UserService extends BaseService {
  find(value) { return this.normalize(value); }
  normalize(value) { return value.trim(); }
}
