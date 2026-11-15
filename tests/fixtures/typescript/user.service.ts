export interface Finder {
  find(value: string): string;
}

export class UserService implements Finder {
  find(value: string): string {
    return value.trim();
  }
}
