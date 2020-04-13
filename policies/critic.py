import torch
import torch.nn as nn
import torch.nn.functional as F

from policies.base import Net

import numpy as np
def fanin_init(size, fanin=None):
    fanin = fanin or size[0]
    v = 1. / np.sqrt(fanin)
    return torch.Tensor(size).uniform_(-v, v)

# The base class for a critic. Includes functions for normalizing reward and state (optional)
class Critic(Net):
  def __init__(self):
    super(Critic, self).__init__()

    self.welford_reward_mean = 0.0
    self.welford_reward_mean_diff = 1.0
    self.welford_reward_n = 1

  def forward(self):
    raise NotImplementedError

class FF_Q(Critic):
  def __init__(self, state_dim, action_dim, layers=(256, 256), env_name='NOT SET', normc_init=True):
    super(FF_Q, self).__init__()

    self.critic_layers = nn.ModuleList()
    self.critic_layers += [nn.Linear(state_dim + action_dim, layers[0])]
    for i in range(len(layers)-1):
        self.critic_layers += [nn.Linear(layers[i], layers[i+1])]
    self.network_out = nn.Linear(layers[-1], 1)

    self.env_name = env_name

    if normc_init:
      self.initialize_parameters()

  def forward(self, state, action):
    x = torch.cat([state, action], len(state.size())-1)

    for idx, layer in enumerate(self.critic_layers):
      x = F.relu(layer(x))

    return self.network_out(x)

class FF_V(Critic):
  def __init__(self, state_dim, layers=(256, 256), env_name='NOT SET', normc_init=True):
    super(FF_V, self).__init__()

    self.critic_layers = nn.ModuleList()
    self.critic_layers += [nn.Linear(state_dim, layers[0])]
    for i in range(len(layers)-1):
        self.critic_layers += [nn.Linear(layers[i], layers[i+1])]
    self.network_out = nn.Linear(layers[-1], 1)

    self.env_name = env_name

    if normc_init:
      self.initialize_parameters()

  def forward(self, state):

    x = state
    for idx, layer in enumerate(self.critic_layers):
      x = F.relu(layer(x))

    #print("FF_V is returning size {} from input {}".format(x.size(), state.size()))
    return self.network_out(x)

class LSTM_Q(Critic):
  def __init__(self, input_dim, action_dim, layers=(128, 128), env_name='NOT SET', normc_init=True):
    super(LSTM_Q, self).__init__()

    self.critic_layers = nn.ModuleList()
    self.critic_layers += [nn.LSTMCell(input_dim + action_dim, layers[0])]
    for i in range(len(layers)-1):
        self.critic_layers += [nn.LSTMCell(layers[i], layers[i+1])]
    self.network_out = nn.Linear(layers[-1], 1)

    self.init_hidden_state()

    self.is_recurrent = True
    self.env_name = env_name

    if normc_init:
      self.initialize_parameters()

  def get_hidden_state(self):
    return self.hidden, self.cells

  def init_hidden_state(self, batch_size=1):
    self.hidden = [torch.zeros(batch_size, l.hidden_size) for l in self.critic_layers]
    self.cells  = [torch.zeros(batch_size, l.hidden_size) for l in self.critic_layers]
  
  def forward(self, state, action):
    dims = len(state.size())

    if len(state.size()) != len(action.size()):
      print("state and action must have same number of dimensions: {} vs {}", state.size(), action.size())
      exit(1)

    if dims == 3: # if we get a batch of trajectories
      self.init_hidden_state(batch_size=state.size(1))
      value = []
      for t, (state_batch_t, action_batch_t) in enumerate(zip(state, action)):
        x_t = torch.cat([state_batch_t, action_batch_t], 1)

        for idx, layer in enumerate(self.critic_layers):
          c, h = self.cells[idx], self.hidden[idx]
          self.hidden[idx], self.cells[idx] = layer(x_t, (h, c))
          x_t = self.hidden[idx]
        x_t = self.network_out(x_t)
        value.append(x_t)

      x = torch.stack([a.float() for a in value])

    else:

      x = torch.cat([state, action], len(state_t.size()))
      if dims == 1:
        x = x.view(1, -1)

      for idx, layer in enumerate(self.critic_layers):
        c, h = self.cells[idx], self.hidden[idx]
        self.hidden[idx], self.cells[idx] = layer(x_t, (h, c))
        x = self.hidden[idx]
      x = self.network_out(x)
      
      if dims == 1:
        x = x.view(-1)

    return x

class LSTM_V(Critic):
  def __init__(self, input_dim, layers=(128, 128), env_name='NOT SET', normc_init=True):
    super(LSTM_V, self).__init__()

    self.critic_layers = nn.ModuleList()
    self.critic_layers += [nn.LSTMCell(input_dim, layers[0])]
    for i in range(len(layers)-1):
        self.critic_layers += [nn.LSTMCell(layers[i], layers[i+1])]
    self.network_out = nn.Linear(layers[-1], 1)

    self.init_hidden_state()

    self.is_recurrent = True
    self.env_name = env_name

    if normc_init:
      self.initialize_parameters()

  def get_hidden_state(self):
    return self.hidden, self.cells

  def init_hidden_state(self, batch_size=1):
    self.hidden = [torch.zeros(batch_size, l.hidden_size) for l in self.critic_layers]
    self.cells  = [torch.zeros(batch_size, l.hidden_size) for l in self.critic_layers]
  
  def forward(self, state):
    dims = len(state.size())

    if dims == 3: # if we get a batch of trajectories
      self.init_hidden_state(batch_size=state.size(1))
      value = []
      for t, state_batch_t in enumerate(state):
        x_t = state_batch_t
        for idx, layer in enumerate(self.critic_layers):
          c, h = self.cells[idx], self.hidden[idx]
          self.hidden[idx], self.cells[idx] = layer(x_t, (h, c))
          x_t = self.hidden[idx]
        x_t = self.network_out(x_t)
        value.append(x_t)

      x = torch.stack([a.float() for a in value])

    else:
      x = state
      if dims == 1:
        x = x.view(1, -1)

      for idx, layer in enumerate(self.critic_layers):
        c, h = self.cells[idx], self.hidden[idx]
        self.hidden[idx], self.cells[idx] = layer(x, (h, c))
        x = self.hidden[idx]
      x = self.network_out(x)

      if dims == 1:
        x = x.view(-1)

    return x

class GRU_Q(Critic):
  def __init__(self, input_dim, action_dim, layers=(128, 128), env_name='NOT SET', normc_init=True):
    super(GRU_Q, self).__init__()

    self.critic_layers = nn.ModuleList()
    self.critic_layers += [nn.GRUCell(input_dim + action_dim, layers[0])]
    for i in range(len(layers)-1):
        self.critic_layers += [nn.GRUCell(layers[i], layers[i+1])]
    self.network_out = nn.Linear(layers[-1], 1)

    self.init_hidden_state()

    self.is_recurrent = True
    self.env_name = env_name

    if normc_init:
      self.initialize_parameters()

  def get_hidden_state(self):
    return self.hidden

  def init_hidden_state(self, batch_size=1):
    self.hidden = [torch.zeros(batch_size, l.hidden_size) for l in self.critic_layers]
  
  def forward(self, state, action):
    dims = len(state.size())

    if len(state.size()) != len(action.size()):
      print("state and action must have same number of dimensions: {} vs {}", state.size(), action.size())
      exit(1)

    if dims == 3: # if we get a batch of trajectories
      self.init_hidden_state(batch_size=state.size(1))
      value = []
      for t, (state_batch_t, action_batch_t) in enumerate(zip(state, action)):
        x_t = torch.cat([state_batch_t, action_batch_t], 1)

        for idx, layer in enumerate(self.critic_layers):
          h = self.hidden[idx]
          self.hidden[idx] = layer(x_t, h)
          x_t = self.hidden[idx]
        x_t = self.network_out(x_t)
        value.append(x_t)

      x = torch.stack([a.float() for a in value])

    else:

      x = torch.cat([state, action], len(state_t.size()))
      if dims == 1:
        x = x.view(1, -1)

      for idx, layer in enumerate(self.critic_layers):
        h = self.hidden[idx]
        self.hidden[idx] = layer(x_t, h)
        x = self.hidden[idx]
      x = self.network_out(x)
      
      if dims == 1:
        x = x.view(-1)

    return x

class GRU_V(Critic):
  def __init__(self, input_dim, layers=(128, 128), env_name='NOT SET', normc_init=True):
    super(GRU_V, self).__init__()

    self.critic_layers = nn.ModuleList()
    self.critic_layers += [nn.GRUCell(input_dim, layers[0])]
    for i in range(len(layers)-1):
        self.critic_layers += [nn.GRUCell(layers[i], layers[i+1])]
    self.network_out = nn.Linear(layers[-1], 1)

    self.init_hidden_state()

    self.is_recurrent = True
    self.env_name = env_name

    if normc_init:
      self.initialize_parameters()

  def get_hidden_state(self):
    return self.hidden

  def init_hidden_state(self, batch_size=1):
    self.hidden = [torch.zeros(batch_size, l.hidden_size) for l in self.critic_layers]
  
  def forward(self, state):
    dims = len(state.size())

    if dims == 3: # if we get a batch of trajectories
      self.init_hidden_state(batch_size=state.size(1))
      value = []
      for t, state_batch_t in enumerate(state):
        x_t = state_batch_t
        for idx, layer in enumerate(self.critic_layers):
          h = self.hidden[idx]
          self.hidden[idx] = layer(x_t, h)
          x_t = self.hidden[idx]
        x_t = self.network_out(x_t)
        value.append(x_t)

      x = torch.stack([a.float() for a in value])

    else:
      x = state
      if dims == 1:
        x = x.view(1, -1)

      for idx, layer in enumerate(self.critic_layers):
        h = self.hidden[idx]
        self.hidden[idx] = layer(x, h)
        x = self.hidden[idx]
      x = self.network_out(x)

      if dims == 1:
        x = x.view(-1)

    return x
