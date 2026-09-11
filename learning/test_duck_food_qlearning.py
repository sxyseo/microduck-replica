import contextlib
import io
import unittest

import duck_food_qlearning as demo


class DuckFoodQLearningTests(unittest.TestCase):
    def test_public_learning_components_exist(self):
        self.assertTrue(hasattr(demo, "LineWorld"))
        self.assertTrue(hasattr(demo, "QLearningAgent"))
        self.assertTrue(hasattr(demo, "train"))
        self.assertTrue(hasattr(demo, "evaluate"))

    def test_world_stops_at_edges_and_rewards_food(self):
        world = demo.LineWorld(length=7, food_position=6)

        state, reward, done = world.step(-1)
        self.assertEqual((state, reward, done), (0, -0.2, False))

        world.position = 5
        state, reward, done = world.step(1)
        self.assertEqual((state, reward, done), (6, 10.0, True))

    def test_training_learns_to_reach_food(self):
        world = demo.LineWorld(length=7, food_position=6)
        agent = demo.QLearningAgent(state_count=7, seed=7)

        demo.train(world, agent, episodes=400)
        route, total_reward = demo.evaluate(world, agent)

        self.assertEqual(route, [0, 1, 2, 3, 4, 5, 6])
        self.assertGreater(total_reward, 9.0)

    def test_main_prints_learned_route(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = demo.main(["--episodes", "400", "--seed", "7"])

        self.assertEqual(exit_code, 0)
        self.assertIn("训练后的路线", output.getvalue())
        self.assertIn("🦆", output.getvalue())
        self.assertIn("🌽", output.getvalue())


if __name__ == "__main__":
    unittest.main()
