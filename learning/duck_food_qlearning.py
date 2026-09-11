"""A dependency-free reinforcement-learning experiment for Microduck.

The learning algorithm only talks to an environment through ``reset`` and
``step``.  A later hardware experiment can therefore replace ``LineWorld``
with a servo-and-camera environment without rewriting Q-learning itself.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from typing import Sequence


ACTIONS = (-1, 1)
ACTION_NAMES = {-1: "向左", 1: "向右"}


@dataclass
class LineWorld:
    """A duck moving along a line until it reaches the food."""

    length: int = 7
    food_position: int = 6
    position: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.length < 2:
            raise ValueError("length must be at least 2")
        if not 0 < self.food_position < self.length:
            raise ValueError("food_position must be inside the world and after the start")

    def reset(self) -> int:
        self.position = 0
        return self.position

    def step(self, action: int) -> tuple[int, float, bool]:
        if action not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}")

        next_position = min(self.length - 1, max(0, self.position + action))
        hit_edge = next_position == self.position
        self.position = next_position

        if self.position == self.food_position:
            return self.position, 10.0, True
        return self.position, (-0.2 if hit_edge else -0.1), False

    def render(self, duck_position: int | None = None) -> str:
        position = self.position if duck_position is None else duck_position
        cells = ["□"] * self.length
        cells[self.food_position] = "🌽"
        cells[position] = "🦆🌽" if position == self.food_position else "🦆"
        return " ".join(cells)


class QLearningAgent:
    """A small tabular Q-learning agent with left/right actions."""

    def __init__(
        self,
        state_count: int,
        *,
        learning_rate: float = 0.2,
        discount: float = 0.95,
        seed: int = 7,
    ) -> None:
        self.q_values = [[0.0, 0.0] for _ in range(state_count)]
        self.learning_rate = learning_rate
        self.discount = discount
        self.random = random.Random(seed)

    def choose_action(self, state: int, epsilon: float) -> int:
        if self.random.random() < epsilon:
            return self.random.choice(ACTIONS)
        return self.best_action(state)

    def best_action(self, state: int) -> int:
        left_value, right_value = self.q_values[state]
        return 1 if right_value >= left_value else -1

    def learn(
        self,
        state: int,
        action: int,
        reward: float,
        next_state: int,
        done: bool,
    ) -> None:
        action_index = ACTIONS.index(action)
        current = self.q_values[state][action_index]
        future = 0.0 if done else max(self.q_values[next_state])
        target = reward + self.discount * future
        self.q_values[state][action_index] += self.learning_rate * (target - current)


def train(world: LineWorld, agent: QLearningAgent, episodes: int = 400) -> list[float]:
    """Train the agent and return each episode's reward."""

    rewards: list[float] = []
    max_steps = world.length * 4

    for episode in range(episodes):
        state = world.reset()
        total_reward = 0.0
        epsilon = max(0.05, 1.0 - episode / max(1, episodes * 0.8))

        for _ in range(max_steps):
            action = agent.choose_action(state, epsilon)
            next_state, reward, done = world.step(action)
            agent.learn(state, action, reward, next_state, done)
            state = next_state
            total_reward += reward
            if done:
                break

        rewards.append(total_reward)

    return rewards


def evaluate(
    world: LineWorld,
    agent: QLearningAgent,
    max_steps: int | None = None,
) -> tuple[list[int], float]:
    """Run the learned policy once without exploration."""

    state = world.reset()
    route = [state]
    total_reward = 0.0

    for _ in range(max_steps or world.length * 2):
        action = agent.best_action(state)
        state, reward, done = world.step(action)
        route.append(state)
        total_reward += reward
        if done:
            break

    return route, total_reward


def format_q_table(agent: QLearningAgent) -> str:
    lines = ["位置 | 向左 Q 值 | 向右 Q 值 | 学到的动作"]
    for position, (left, right) in enumerate(agent.q_values):
        action = ACTION_NAMES[agent.best_action(position)]
        lines.append(f" {position:>2}  | {left:>9.3f} | {right:>9.3f} | {action}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="让小鸭用 Q-learning 学会找到玉米")
    parser.add_argument("--episodes", type=int, default=400, help="训练轮数，默认 400")
    parser.add_argument("--seed", type=int, default=7, help="随机种子，默认 7")
    args = parser.parse_args(argv)

    if args.episodes <= 0:
        parser.error("--episodes 必须大于 0")

    world = LineWorld()
    agent = QLearningAgent(state_count=world.length, seed=args.seed)

    print("初始场景：")
    print(world.render(0))
    print("\n开始训练（探索时会左右乱走）……")
    rewards = train(world, agent, episodes=args.episodes)
    route, total_reward = evaluate(world, agent)

    print(f"完成 {args.episodes} 轮训练，最后 20 轮平均奖励：{sum(rewards[-20:]) / min(20, len(rewards)):.2f}")
    print("\n学到的 Q 表：")
    print(format_q_table(agent))
    print("\n训练后的路线：")
    print(" → ".join(map(str, route)))
    print(world.render(route[-1]))
    print(f"本次总奖励：{total_reward:.2f}")
    print("\n硬件升级方向：位置→舵机角度，左右动作→转动舵机，奖励→摄像头目标居中程度。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
