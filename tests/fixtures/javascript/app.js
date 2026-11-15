import express from 'express';
import { UserService } from './service.js';

const router = express.Router();

function requireAuth(req, res, next) { next(); }

router.get('/users/:id', requireAuth, (req, res) => {
  const users = new UserService();
  res.send(users.find(req.params.id));
});

export default router;
