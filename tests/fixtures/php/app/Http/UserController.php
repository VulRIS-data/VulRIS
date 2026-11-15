<?php
namespace App\Http\Controllers;

use App\Services\UserService;
use Illuminate\Http\Request;

class UserController
{
    public function __construct(private UserService $users)
    {
    }

    public function show(Request $request, string $id)
    {
        $this->authorize('view-user');
        return $this->users->find($request->input('name', $id));
    }
}
