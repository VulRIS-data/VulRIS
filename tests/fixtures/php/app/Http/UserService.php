<?php
namespace App\Services;

interface Finder
{
    public function find(string $value): string;
}

class UserService implements Finder
{
    public function find(string $value): string
    {
        return trim($value);
    }
}
