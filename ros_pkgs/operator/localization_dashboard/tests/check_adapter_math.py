# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Exercise adapter transform math without importing ROS. Run with Python 3.12+."""
import ast
import math
import pathlib
import unittest

path = pathlib.Path(__file__).parents[1] / 'adapters' / 'lio_adapter.py'
module = ast.parse(path.read_text(encoding='utf-8-sig'))
functions = [node for node in module.body if isinstance(node, ast.FunctionDef)
             and node.name in ('multiply', 'quat', 'compose')]
scope = {'math': math}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)


class AdapterMathTest(unittest.TestCase):
    def test_parent_rotation_and_body_extrinsic(self):
        # map<-odom: translate +10x then rotate +90deg; odom<-IMU +2x;
        # IMU<-base +1x. Correct base location is map (10,3,0).
        q = (0., 0., math.sqrt(.5), math.sqrt(.5))
        identity = (0., 0., 0., 1.)
        result = scope['compose'](scope['compose'](((10., 0., 0.), q),
                   ((2., 0., 0.), identity)), ((1., 0., 0.), identity))
        for actual, expected in zip(result[0], (10., 3., 0.)):
            self.assertAlmostEqual(actual, expected)

    def test_invalid_quaternion(self):
        from types import SimpleNamespace
        with self.assertRaises(ValueError):
            scope['quat'](SimpleNamespace(x=0, y=0, z=0, w=0))


if __name__ == '__main__':
    unittest.main()
