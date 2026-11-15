import { Controller, Get, Param, UseGuards } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { UserService } from './user.service';

@Controller('users')
export class UserController {
  constructor(private readonly users: UserService) {}

  @Get(':id')
  @UseGuards(AuthGuard('jwt'))
  get(@Param('id') id: string) {
    return this.users.find(id);
  }
}
