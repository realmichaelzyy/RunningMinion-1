import os
import logging
import time
import numpy as np
import matplotlib.pyplot as plt

# PLE imports
from ple.games.minion import RunningMinion
from ple import PLE
from six.moves import cPickle

# local imports
import utils
import naive
import agent


def process_state(state):
    state = np.array([state.values()])
    # state = state[0, 0:4]
    #max_values = np.array([288.0, 50.0, 288.0, 512.0, 512.0, 288, 512.0, 512.0])
    max_values = np.array([512.0, 512.0,512.0])
    state = state / max_values
    # print state

    return state


def init_agent(env):
    # agent settings
    batch_size = 20
    num_frames = 1  # number of frames in a 'state'
    frame_skip = 2
    lr = 0.01
    discount = 0.95  # discount factor
    # rng = np.random.RandomState(int(time.time()))
    rng = np.random.RandomState(24)

    # my_agent = naive.NaiveAgent(allowed_actions=env.getActionSet())
    my_agent = agent.Agent(env, batch_size, num_frames, frame_skip, lr, discount, rng, optimizer="sgd_nesterov")
    # my_agent = utils.DQNAgent(env, batch_size, num_frames, frame_skip, lr, discount, rng, optimizer="sgd_nesterov")
    my_agent.build_model()

    return my_agent


def plot_figure(fig_path, data, label, name, num_steps_train):
    plt.figure()
    plt.plot(data)

    plt.xlabel('episode')
    plt.ylabel(label)
    plt.savefig(os.path.join(fig_path, name+'_'+str(num_steps_train)+'.png'))
    # plt.show()
    plt.close()


def plot_result(fig_path, training_rounds, avg_rewards):
    plt.figure()
    plt.plot(training_rounds, avg_rewards)
    plt.xlabel('training rounds')
    plt.ylabel('average reward')
    plt.savefig(os.path.join(fig_path, 'testing.png'))
    plt.close()


def save_agent(my_agent, agent_file_path, agent_file_name):
    my_agent.model.save_weights(os.path.join(agent_file_path, agent_file_name+'_weights.h5'), overwrite=True)
    with open(os.path.join(agent_file_path, agent_file_name+'.pkl'), 'wb') as handle:
        cPickle.dump(my_agent, handle, cPickle.HIGHEST_PROTOCOL)


def load_agent(env, agent_file_path, agent_file_name):
    with open(os.path.join(agent_file_path, agent_file_name+'.pkl'), 'rb') as handle:
        my_agent = cPickle.load(handle)
        my_agent.env = env

    my_agent.model.load_weights(os.path.join(agent_file_path, agent_file_name+'_weights.h5'))
    return my_agent


def play_with_saved_agent(agent_file_path, agent_file_name, test_rounds=20):
    game = RunningMinion()
    env = PLE(game, fps=30, display_screen=True, force_fps=True, state_preprocessor=process_state)
    my_agent = load_agent(env, agent_file_path, agent_file_name)
    env.init()

    print "Testing model:", agent_file_name

    total_reward = 0.0
    for _ in range(test_rounds):
        my_agent.start_episode()
        episode_reward = 0.0
        while env.game_over() == False:
            state = env.getGameState()
            reward, action = my_agent.act(state, epsilon=0.00)
            episode_reward += reward

        print "Agent score {:0.1f} reward for episode.".format(episode_reward)
        total_reward += episode_reward
        my_agent.end_episode()

    return total_reward/test_rounds


def agent_training(agent_file_path, agent_file_name, fig_path, num_steps_train_total = 5000):
    # training parameters
    num_epochs = 5
    num_steps_train_epoch = num_steps_train_total/num_epochs  # steps per epoch of training
    num_steps_test = 100
    update_frequency = 10  # step frequency of model training/updates

    epsilon = 0.15  # percentage of time we perform a random action, help exploration.
    epsilon_steps = 1000  # decay steps
    epsilon_min = 0.1
    epsilon_rate = (epsilon - epsilon_min) / epsilon_steps

    # memory settings
    max_memory_size = 10000
    min_memory_size = 60  # number needed before model training starts

    game = RunningMinion()
    env = PLE(game, fps=30, display_screen=True, force_fps=True, state_preprocessor=process_state)
    my_agent = init_agent(env)

    memory = utils.ReplayMemory(max_memory_size, min_memory_size)
    env.init()

    # Logging configuration and figure plotting
    logging.basicConfig(filename='../learning.log', filemode='w',
                        level=logging.DEBUG, format='%(levelname)s:%(message)s')
    logging.info('========================================================')
    logging.info('Training started for total training steps: '+str(num_steps_train_total)+'.\n')
    learning_rewards = [0]
    testing_rewards = [0]

    for epoch in range(1, num_epochs + 1):
        steps, num_episodes = 0, 0
        losses, rewards = [], []
        env.display_screen = False

        # training loop
        while steps < num_steps_train_epoch:
            episode_reward = 0.0
            my_agent.start_episode()

            while env.game_over() == False and steps < num_steps_train_epoch:
                state = env.getGameState()
                reward, action = my_agent.act(state, epsilon=epsilon)
                memory.add([state, action, reward, env.game_over()])

                if steps % update_frequency == 0:
                    loss = memory.train_agent_batch(my_agent)

                    if loss is not None:
                        losses.append(loss)
                        epsilon = np.max(epsilon_min, epsilon - epsilon_rate)

                episode_reward += reward
                steps += 1

            if steps < num_steps_train_epoch:
                learning_rewards.append(episode_reward)

            if num_episodes % 5 == 0:
                # print "Episode {:01d}: Reward {:0.1f}".format(num_episodes, episode_reward)
                logging.info("Episode {:01d}: Reward {:0.1f}".format(num_episodes, episode_reward))

            rewards.append(episode_reward)
            num_episodes += 1
            my_agent.end_episode()

        logging.info("Train Epoch {:02d}: Epsilon {:0.4f} | Avg. Loss {:0.3f} | Avg. Reward {:0.3f}\n"
                     .format(epoch, epsilon, np.mean(losses), np.sum(rewards) / num_episodes))

        steps, num_episodes = 0, 0
        losses, rewards = [], []

        # testing loop
        while steps < num_steps_test:
            episode_reward = 0.0
            my_agent.start_episode()

            while env.game_over() == False and steps < num_steps_test:
                state = env.getGameState()
                reward, action = my_agent.act(state, epsilon=0.05)

                episode_reward += reward
                testing_rewards.append(testing_rewards[-1]+reward)
                steps += 1

                # done watching after 500 steps.
                if steps > 500:
                    env.display_screen = False

            if num_episodes % 5 == 0:
                logging.info("Episode {:01d}: Reward {:0.1f}".format(num_episodes, episode_reward))

            if steps < num_steps_test:
                testing_rewards.append(episode_reward)

            rewards.append(episode_reward)
            num_episodes += 1
            my_agent.end_episode()

        logging.info("Test Epoch {:02d}: Best Reward {:0.3f} | Avg. Reward {:0.3f}\n"
                     .format(epoch, np.max(rewards), np.sum(rewards) / num_episodes))

    logging.info("Training complete.\n\n")
    plot_figure(fig_path, learning_rewards, 'reward', 'reward_in_training', num_steps_train_total)
    plot_figure(fig_path, testing_rewards, 'reward', 'reward_in_testing', num_steps_train_total)

    save_agent(my_agent, agent_file_path, agent_file_name)


def main_naive():
    game = FlappyBird()
    env = PLE(game, fps=30, display_screen=True)
    my_agent = naive.NaiveAgent(allowed_actions=env.getActionSet())

    env.init()
    reward = 0.0
    nb_frames = 10000

    for i in range(nb_frames):
        if env.game_over():
            env.reset_game()

        observation = env.getScreenRGB()
        action = my_agent.pickAction(reward, observation)
        reward = env.act(action)


def main():
    agent_file_path = '../results/'
    agent_file_name_base = 'my_agent'
    fig_path = '../figures/'
    # training_rounds = [1000, 5000, 10000, 25000]
    training_rounds =[5000]
    avg_rewards = list()

    # for num_steps_train_total in training_rounds:
    #     agent_file_name = agent_file_name_base+'_'+str(num_steps_train_total)
    #     agent_training(agent_file_path, agent_file_name, fig_path, num_steps_train_total)

    for num_steps_train_total in training_rounds:
        agent_file_name = agent_file_name_base+'_'+str(num_steps_train_total)
        avg_reward = play_with_saved_agent(agent_file_path, agent_file_name, 3)
        avg_rewards.append(avg_reward)

    plot_result(fig_path, training_rounds, avg_rewards)


if __name__ == '__main__':
    main()
