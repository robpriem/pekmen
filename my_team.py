from collections import deque

from capture_agents import CaptureAgent
from game import Directions


def create_team(first_index, second_index, is_red,
                first='OffensiveAgent', second='OffensiveAgent', num_training=0):
    return [eval(first)(first_index), eval(second)(second_index)]


class OffensiveAgent(CaptureAgent):

    def register_initial_state(self, game_state):
        super().register_initial_state(game_state)

        
        self.start = game_state.get_agent_position(self.index)
        self.boundary = self._compute_boundary_positions(game_state)
        self.boundary_home = min(
            self.boundary,
            key=lambda p: abs(p[1] - (game_state.data.layout.height // 2))
        ) if self.boundary else self.start
        self.anchor = self.boundary_home
        self.upper_anchor, self.lower_anchor = self._compute_lane_anchors(game_state)

        # Searchdieptes: self-search en minimax dichtbij threats.
        self.search_depth = 2
        self.min_max_depth = 2

        
        self.return_food_threshold = 5
        self.close_quarters_distance = 5
        self.danger_dist = 3
        self.endgame_return_buffer = 35
        self.visible_defenders_indices = []

        # Nieuwe parameters
        self.defender_tactical_radius = 5
        self.invader_tactical_radius = 5
        self.low_time_buffer = 120
        self.max_carry_before_return = 8
        self.deep_food_penalty_dist = 20
        self.capsule_tactical_radius = 5
        self.missing_food_weight = 0
        self.anchor_weight_base = 0.0
        self.noisy_enemy_close = 3
        self.noisy_enemy_mid = 5

        # extra opponent-info.
        self.last_defended_food = self.get_food_you_are_defending(game_state).as_list()
        self.missing_food_hint = []
        self.last_seen_enemy_positions = {}

        self.recent_positions = deque(maxlen=8)
        if self.start is not None:
            self.recent_positions.append(self.start)

    def choose_action(self, game_state):
        return self.choose_action_offensive(game_state)

    def choose_action_offensive(self, game_state):
        # Zichtbare defenders en extra opponent-info updaten.
        self.visible_defenders_indices = self.get_visible_opponents(game_state)
        self._update_last_seen_enemy_positions(game_state)
        self._update_missing_food_hint(game_state)

        current_pos = game_state.get_agent_position(self.index)
        if current_pos is not None:
            self.recent_positions.append(current_pos)

        enemies = self.get_opponents(game_state)
        chasing_enemies = any(game_state.get_agent_state(i).scared_timer > 0 for i in enemies)

        def OffensiveEval_general(self, game_state):
            my_state = game_state.get_agent_state(self.index)
            my_pos = game_state.get_agent_position(self.index)
            if my_state is None or my_pos is None:
                return 0.0

            time_left = getattr(game_state.data, "timeleft", 0)
            carrying = my_state.num_carrying
            score = self.get_score(game_state)
            food = self.get_food(game_state).as_list()
            food_left = len(food)
            capsules = self.get_capsules(game_state)
            team_dist = self._get_distance_to_closest_teammate(game_state)
            boundary_dist = self._distance_to_boundary(my_pos)
            visible_invaders = self.get_visible_invaders(game_state)
            min_invader_dist = self._min_distance_to_positions(
                my_pos,
                [game_state.get_agent_position(i) for i in visible_invaders if game_state.get_agent_position(i) is not None]
            )

            repeated_visits = self.recent_positions.count(my_pos)

            food_dist_min = min((self.get_maze_distance(my_pos, f) for f in food), default=0)
            capsule_dist_min = min((self.get_maze_distance(my_pos, c) for c in capsules), default=0)
            food_cluster = sum(1 for f in food if self.get_maze_distance(my_pos, f) <= 3)
            enemy_dist = self._get_min_distances_to_enemies(game_state)
            deep_food_penalty = self._deep_food_penalty(game_state, my_pos)

            offensivescore = 0.0

            offensivescore += 60 * score
            offensivescore += 6 * carrying
            offensivescore += -12 * food_dist_min
            offensivescore += -32 * food_left
            offensivescore += 8 * food_cluster
            offensivescore += -0.05 * deep_food_penalty

            # Capsules: belangrijker bij pressure of haalbare chase.
            if self.visible_defenders_indices and enemy_dist <= self.capsule_tactical_radius:
                offensivescore += -0.5 * capsule_dist_min
            elif self._enemy_scared_reachable(game_state, my_pos):
                offensivescore += -0.25 * capsule_dist_min

            # Eindspel en return-home druk continu i.p.v. harde switch.
            endgame_pressure = max(0, self.endgame_return_buffer - time_left)
            bank_urgency = 0.0
            bank_urgency += 1.6 * carrying
            bank_urgency += 0.8 * max(0, 3 - food_left)
            bank_urgency += max(0, self.low_time_buffer - time_left) / 18.0
            if score > 0:
                bank_urgency += 2.0
            if self.visible_defenders_indices and enemy_dist <= 4:
                bank_urgency += 10.0
            if self.visible_defenders_indices and enemy_dist <= 2:
                bank_urgency += 12.0
            if carrying >= 3:
                bank_urgency += 4.0
            if carrying >= 5:
                bank_urgency += 8.0
            if carrying >= self.max_carry_before_return:
                bank_urgency += 12.0
            offensivescore += -bank_urgency * boundary_dist
            offensivescore += -0.18 * endgame_pressure * boundary_dist

            # Team spacing: enkel crowding straffen.
            if team_dist <= 1:
                offensivescore -= 70
            elif team_dist <= 3:
                offensivescore -= 30

            # Anchor: stabiliseert positionering als er geen directe tactische reden is.
            if self.anchor_weight_base > 0 and not self.visible_defenders_indices and not visible_invaders:
                lane_anchor = self.upper_anchor if self.index % 2 == 0 else self.lower_anchor
                target_anchor = lane_anchor if lane_anchor is not None else self.anchor
                if target_anchor is not None:
                    offensivescore += -self.anchor_weight_base * self.get_maze_distance(my_pos, target_anchor)

            # Missing food hint: verdedig harder als er iets verdwenen is.
            if self.missing_food_hint and not food and self.missing_food_weight > 0:
                missing_target = min(self.missing_food_hint, key=lambda p: self.get_maze_distance(my_pos, p))
                offensivescore += -self.missing_food_weight * self.get_maze_distance(my_pos, missing_target)

            # Zichtbare invader dichtbij => defense zwaarder laten meewegen zelfs in offensive mode.
            if min_invader_dist is not None and min_invader_dist <= 2:
                offensivescore -= 8 + 2 * min_invader_dist

            # Anti-oscillatie: recente tiles en direct omkeren zacht straffen,
            # maar die straf verlagen als een defender dichtbij zichtbaar is.
            repeat_penalty = self._get_repeat_penalty(game_state)
            reverse_penalty = self._get_reverse_penalty(game_state)

            if repeated_visits >= 2:
                offensivescore -= repeat_penalty * (repeated_visits + 1)

            previous_observation = self.get_previous_observation()
            if previous_observation is not None:
                previous_state = previous_observation.get_agent_state(self.index)
                previous_direction = previous_state.configuration.direction if previous_state and previous_state.configuration else None
                current_direction = my_state.configuration.direction if my_state and my_state.configuration else None
                if previous_direction is not None and current_direction == Directions.REVERSE[previous_direction]:
                    offensivescore -= reverse_penalty

            return offensivescore

        def OffensiveEval_normal(self, game_state):
            # Dreiging: zichtbare defenders zwaar, noisy distances en last seen info lichter.
            enemy_dist = self._get_min_distances_to_enemies(game_state)
            noisy_dist = self._get_min_noisy_enemy_distance(game_state)
            estimated_dist = self._get_min_estimated_enemy_distance(game_state)

            danger = 0.0
            if self.visible_defenders_indices:
                if enemy_dist <= 1:
                    danger -= 250.0
                elif enemy_dist <= 2:
                    danger -= 120.0
                elif enemy_dist <= 3:
                    danger -= 50.0
                elif enemy_dist <= 5:
                    danger -= 15.0

            if noisy_dist is not None:
                if noisy_dist <= self.noisy_enemy_close:
                    danger -= 22.0
                elif noisy_dist <= self.noisy_enemy_mid:
                    danger -= 10.0

            if estimated_dist is not None and not self.visible_defenders_indices:
                if estimated_dist <= 4:
                    danger -= 12.0
                elif estimated_dist <= 6:
                    danger -= 6.0

            return danger

        def OffensiveEval_chase(self, game_state):
            # Chase alleen belonen als scared enemy effectief haalbaar is.
            my_pos = game_state.get_agent_position(self.index)
            if my_pos is None:
                return 0.0

            chase_score = 0.0
            for i in self.get_opponents(game_state):
                st = game_state.get_agent_state(i)
                pos = st.get_position()
                if pos is None or st.scared_timer <= 0:
                    continue
                dist = self.get_maze_distance(my_pos, pos)
                chase_reachability = st.scared_timer - dist
                chase_score = max(chase_score, 18.0 * max(0, chase_reachability) - 6.0 * dist)

            return chase_score

        ############### NORMAL SEARCH AND MIN-MAX SEARCH ###############

        def Offensive_min_max(self, game_state, eval_function):
            best_action = None
            best_value = float("-inf")
            alpha = float("-inf")
            beta = float("inf")

            actions = game_state.get_legal_actions(self.index)
            actions = [a for a in actions if a != Directions.STOP] or actions
            if not actions:
                return Directions.STOP

            reverse_dir = self._get_reverse_dir(game_state)
            reverse_penalty = self._get_reverse_penalty(game_state)
            repeat_penalty = self._get_repeat_penalty(game_state)

            current_food = self.get_food(game_state).as_list()
            current_food_count = len(current_food)
            current_food_dist = min(
                (self.get_maze_distance(game_state.get_agent_position(self.index), f) for f in current_food),
                default=0
            ) if game_state.get_agent_position(self.index) is not None else 0
            current_carrying = game_state.get_agent_state(self.index).num_carrying if game_state.get_agent_state(self.index) is not None else 0
            current_boundary_dist = self._distance_to_boundary(game_state.get_agent_position(self.index))

            for action in actions:
                successor = game_state.generate_successor(self.index, action)
                if successor is None:
                    continue
                next_agent = (self.index + 1) % game_state.get_num_agents()
                value = self._alphabeta(successor, 0, next_agent, alpha, beta, eval_function)

                if action == reverse_dir:
                    value -= reverse_penalty

                succ_pos = successor.get_agent_position(self.index)
                if succ_pos is not None:
                    value -= repeat_penalty * self.recent_positions.count(succ_pos)

                successor_food = self.get_food(successor).as_list()
                successor_food_count = len(successor_food)
                successor_food_dist = min(
                    (self.get_maze_distance(succ_pos, f) for f in successor_food),
                    default=0
                ) if succ_pos is not None else 0
                successor_carrying = successor.get_agent_state(self.index).num_carrying if successor.get_agent_state(self.index) is not None else 0
                successor_boundary_dist = self._distance_to_boundary(succ_pos)

                if successor_food_count < current_food_count:
                    value += 320
                elif successor_food_dist < current_food_dist:
                    value += 24 * (current_food_dist - successor_food_dist)

                if current_carrying > 0 and successor_carrying < current_carrying:
                    value += 260
                elif current_carrying >= 3 and successor_boundary_dist < current_boundary_dist:
                    value += 28 * (current_boundary_dist - successor_boundary_dist)

                if value > best_value:
                    best_value = value
                    best_action = action

                alpha = max(alpha, best_value)

            return best_action if best_action is not None else Directions.STOP

        def Offensive_Search(self, game_state, eval_function):
            def Offensive_Normal_Search_inner(self, game_state, depth, acc):
                if depth >= self.search_depth or game_state.is_over():
                    return acc

                actions = game_state.get_legal_actions(self.index)
                actions = [a for a in actions if a != Directions.STOP] or actions
                if not actions:
                    return acc

                reverse_dir = self._get_reverse_dir(game_state)
                reverse_penalty = self._get_reverse_penalty(game_state)
                repeat_penalty = self._get_repeat_penalty(game_state)

                current_food = self.get_food(game_state).as_list()
                current_food_count = len(current_food)
                current_food_dist = min(
                    (self.get_maze_distance(game_state.get_agent_position(self.index), f) for f in current_food),
                    default=0
                ) if game_state.get_agent_position(self.index) is not None else 0
                current_carrying = game_state.get_agent_state(self.index).num_carrying if game_state.get_agent_state(self.index) is not None else 0
                current_boundary_dist = self._distance_to_boundary(game_state.get_agent_position(self.index))

                values = []
                for action in actions:
                    successor = game_state.generate_successor(self.index, action)
                    if successor is None:
                        continue
                    value = Offensive_Normal_Search_inner(
                        self,
                        successor,
                        depth + 1,
                        acc + eval_function(successor)
                    )
                    if action == reverse_dir:
                        value -= reverse_penalty
                    succ_pos = successor.get_agent_position(self.index)
                    if succ_pos is not None:
                        value -= repeat_penalty * self.recent_positions.count(succ_pos)

                    successor_food = self.get_food(successor).as_list()
                    successor_food_count = len(successor_food)
                    successor_food_dist = min(
                        (self.get_maze_distance(succ_pos, f) for f in successor_food),
                        default=0
                    ) if succ_pos is not None else 0
                    successor_carrying = successor.get_agent_state(self.index).num_carrying if successor.get_agent_state(self.index) is not None else 0
                    successor_boundary_dist = self._distance_to_boundary(succ_pos)

                    if successor_food_count < current_food_count:
                        value += 320
                    elif successor_food_dist < current_food_dist:
                        value += 24 * (current_food_dist - successor_food_dist)

                    if current_carrying > 0 and successor_carrying < current_carrying:
                        value += 260
                    elif current_carrying >= 3 and successor_boundary_dist < current_boundary_dist:
                        value += 28 * (current_boundary_dist - successor_boundary_dist)

                    values.append(value)

                return max(values) if values else acc

            actions = game_state.get_legal_actions(self.index)
            actions = [a for a in actions if a != Directions.STOP] or actions
            if not actions:
                return Directions.STOP

            reverse_dir = self._get_reverse_dir(game_state)
            reverse_penalty = self._get_reverse_penalty(game_state)
            repeat_penalty = self._get_repeat_penalty(game_state)

            current_food = self.get_food(game_state).as_list()
            current_food_count = len(current_food)
            current_food_dist = min(
                (self.get_maze_distance(game_state.get_agent_position(self.index), f) for f in current_food),
                default=0
            ) if game_state.get_agent_position(self.index) is not None else 0
            current_carrying = game_state.get_agent_state(self.index).num_carrying if game_state.get_agent_state(self.index) is not None else 0
            current_boundary_dist = self._distance_to_boundary(game_state.get_agent_position(self.index))

            best_action = None
            best_value = float("-inf")
            for action in actions:
                successor = game_state.generate_successor(self.index, action)
                if successor is None:
                    continue
                value = Offensive_Normal_Search_inner(self, successor, 1, eval_function(successor))
                if action == reverse_dir:
                    value -= reverse_penalty
                succ_pos = successor.get_agent_position(self.index)
                if succ_pos is not None:
                    value -= repeat_penalty * self.recent_positions.count(succ_pos)

                successor_food = self.get_food(successor).as_list()
                successor_food_count = len(successor_food)
                successor_food_dist = min(
                    (self.get_maze_distance(succ_pos, f) for f in successor_food),
                    default=0
                ) if succ_pos is not None else 0
                successor_carrying = successor.get_agent_state(self.index).num_carrying if successor.get_agent_state(self.index) is not None else 0
                successor_boundary_dist = self._distance_to_boundary(succ_pos)

                if successor_food_count < current_food_count:
                    value += 360
                elif successor_food_dist < current_food_dist:
                    value += 28 * (current_food_dist - successor_food_dist)

                if current_carrying > 0 and successor_carrying < current_carrying:
                    value += 320
                elif current_carrying >= 3 and successor_boundary_dist < current_boundary_dist:
                    value += 36 * (current_boundary_dist - successor_boundary_dist)

                if value > best_value:
                    best_value = value
                    best_action = action
            return best_action if best_action is not None else Directions.STOP

        #  druk: visible defenders/invaders dichtbij => minimax.
        visible_invaders = self.get_visible_invaders(game_state)
        invader_dist = self._min_distance_to_positions(
            game_state.get_agent_position(self.index),
            [game_state.get_agent_position(i) for i in visible_invaders if game_state.get_agent_position(i) is not None]
        )
        tactical_pressure = (
            (self.visible_defenders_indices and self._get_min_distances_to_enemies(game_state) <= self.defender_tactical_radius)
            or
            (invader_dist is not None and invader_dist <= self.invader_tactical_radius)
        )

        if chasing_enemies and not tactical_pressure:
            return Offensive_Search(self, game_state, lambda s: OffensiveEval_chase(self, s) + OffensiveEval_general(self, s))
        elif chasing_enemies and tactical_pressure:
            return Offensive_min_max(self, game_state, lambda s: OffensiveEval_chase(self, s) + OffensiveEval_general(self, s))
        elif not chasing_enemies and not tactical_pressure:
            return Offensive_Search(self, game_state, lambda s: OffensiveEval_normal(self, s) + OffensiveEval_general(self, s))
        else:
            return Offensive_min_max(self, game_state, lambda s: OffensiveEval_normal(self, s) + OffensiveEval_general(self, s))

    ####################################################### HELPER FUNCTIONS ########################################################

    def get_visible_opponents(self, game_state):
        # Zichtbare defenders op hun eigen helft.
        res = []
        for i in self.get_opponents(game_state):
            st = game_state.get_agent_state(i)
            pos = st.get_position()
            if pos is None:
                continue
            if not st.is_pacman:
                res.append(i)
        return res

    def get_visible_invaders(self, game_state):
        # Zichtbare invaders op onze helft.
        res = []
        for i in self.get_opponents(game_state):
            st = game_state.get_agent_state(i)
            pos = st.get_position()
            if pos is None:
                continue
            if st.is_pacman:
                res.append(i)
        return res

    def get_indices_involved_in_close_quarters(self, game_state):
        # Minimax beperken tot lokaal relevante agents.
        my_pos = game_state.get_agent_position(self.index)
        involved = [self.index]

        if my_pos is None:
            return involved

        for m in self.get_team(game_state):
            if m == self.index:
                continue
            pos = game_state.get_agent_position(m)
            if pos is None:
                continue
            if self.distancer.get_distance(pos, my_pos) < self.close_quarters_distance:
                involved.append(m)

        for i in self.get_visible_opponents(game_state) + self.get_visible_invaders(game_state):
            pos = game_state.get_agent_position(i)
            if pos is None:
                continue
            if self.distancer.get_distance(pos, my_pos) < self.close_quarters_distance:
                involved.append(i)

        return involved

    def _alphabeta(self, state, depth, agent_idx, alpha, beta, eval_function):
        # Algemene alpha-beta voor multi-agent turn-taking.
        if depth >= self.min_max_depth or state.is_over():
            return eval_function(state)

        agent_state = state.get_agent_state(agent_idx)
        if agent_state is None:
            return eval_function(state)

        involved = self.get_indices_involved_in_close_quarters(state)
        num_agents = state.get_num_agents()

        next_agent = (agent_idx + 1) % num_agents
        while next_agent not in involved:
            next_agent = (next_agent + 1) % num_agents

        if agent_state.configuration is None:
            if agent_idx == self.index:
                return eval_function(state)
            return self._alphabeta(state, depth, next_agent, alpha, beta, eval_function)

        legal_actions = state.get_legal_actions(agent_idx)
        legal_actions = [a for a in legal_actions if a != Directions.STOP] or legal_actions
        if not legal_actions:
            return eval_function(state)

        next_depth = depth + 1 if next_agent == self.index else depth

        if agent_idx in self.get_team(state):
            value = float("-inf")
            for action in legal_actions:
                successor = state.generate_successor(agent_idx, action)
                if successor is None:
                    continue
                value = max(
                    value,
                    self._alphabeta(successor, next_depth, next_agent, alpha, beta, eval_function)
                )
                if value >= beta:
                    return value
                alpha = max(alpha, value)
            return value

        elif agent_idx in self.get_opponents(state):
            value = float("+inf")
            for action in legal_actions:
                successor = state.generate_successor(agent_idx, action)
                if successor is None:
                    continue
                value = min(
                    value,
                    self._alphabeta(successor, next_depth, next_agent, alpha, beta, eval_function)
                )
                if value <= alpha:
                    return value
                beta = min(beta, value)
            return value

        return eval_function(state)

    def _compute_boundary_positions(self, game_state):
        walls = game_state.get_walls()
        width = game_state.data.layout.width
        height = game_state.data.layout.height

        if self.red:
            boundary_x = (width // 2) - 1
        else:
            boundary_x = (width // 2)

        boundary = []
        for y in range(height):
            if not walls[boundary_x][y]:
                boundary.append((boundary_x, y))

        return boundary

    def _compute_lane_anchors(self, game_state):
        if not self.boundary:
            return self.start, self.start
        h = game_state.data.layout.height
        upper = min(self.boundary, key=lambda p: abs(p[1] - (2 * h) // 3))
        lower = min(self.boundary, key=lambda p: abs(p[1] - h // 3))
        return upper, lower

    def _distance_to_boundary(self, my_pos):
        if my_pos is None or not self.boundary:
            return 0
        return min(self.get_maze_distance(my_pos, b) for b in self.boundary)

    def _get_reverse_dir(self, game_state):
        my_state = game_state.get_agent_state(self.index)
        if my_state is None or my_state.configuration is None:
            return None
        return Directions.REVERSE[my_state.configuration.direction]

    def _get_reverse_penalty(self, game_state):
        enemy_dist = self._get_min_distances_to_enemies(game_state)
        if self.visible_defenders_indices and enemy_dist <= 3:
            return 0.0
        if self.visible_defenders_indices and enemy_dist <= 5:
            return 2.0
        return 5.0

    def _get_repeat_penalty(self, game_state):
        enemy_dist = self._get_min_distances_to_enemies(game_state)
        if self.visible_defenders_indices and enemy_dist <= 3:
            return 2.0
        if self.visible_defenders_indices and enemy_dist <= 5:
            return 5.0
        return 10.0

    def _get_min_distances_to_enemies(self, game_state):
        # Eerst exacte visible defenders, daarna noisy info.
        visible_opponents = self.get_visible_opponents(game_state)
        my_pos = game_state.get_agent_position(self.index)
        if my_pos is not None and visible_opponents:
            return min(self.get_maze_distance(my_pos, game_state.get_agent_position(i)) for i in visible_opponents)
        return self._get_min_noisy_enemy_distance(game_state) or 0

    def _get_min_noisy_enemy_distance(self, game_state):
        agent_distances = game_state.get_agent_distances()
        if agent_distances is not None:
            vals = [agent_distances[i] for i in self.get_opponents(game_state)]
            return min(vals) if vals else None
        return None

    def _update_last_seen_enemy_positions(self, game_state):
        for i in self.get_opponents(game_state):
            pos = game_state.get_agent_position(i)
            if pos is not None:
                self.last_seen_enemy_positions[i] = pos

    def _get_min_estimated_enemy_distance(self, game_state):
        my_pos = game_state.get_agent_position(self.index)
        if my_pos is None or not self.last_seen_enemy_positions:
            return None
        return min(self.get_maze_distance(my_pos, pos) for pos in self.last_seen_enemy_positions.values())

    def _update_missing_food_hint(self, game_state):
        current_food = self.get_food_you_are_defending(game_state).as_list()
        self.missing_food_hint = [food for food in self.last_defended_food if food not in current_food]
        self.last_defended_food = current_food

    def _enemy_scared_reachable(self, game_state, my_pos):
        if my_pos is None:
            return False
        for i in self.get_opponents(game_state):
            st = game_state.get_agent_state(i)
            pos = st.get_position()
            if pos is None:
                continue
            if st.scared_timer > self.get_maze_distance(my_pos, pos):
                return True
        return False

    def _deep_food_penalty(self, game_state, my_pos):
        # Straf voor geïsoleerde diepe food wanneer die te ver weg ligt van veilige terugkeer.
        food = self.get_food(game_state).as_list()
        if my_pos is None or not food:
            return 0.0
        deep_food = [f for f in food if self.get_maze_distance(my_pos, f) >= self.deep_food_penalty_dist]
        return float(len(deep_food))

    def _min_distance_to_positions(self, my_pos, positions):
        if my_pos is None or not positions:
            return None
        return min(self.get_maze_distance(my_pos, p) for p in positions)

    def _get_distance_to_closest_teammate(self, game_state):
        my_pos = game_state.get_agent_position(self.index)
        if my_pos is None:
            return 0

        teammate_distances = []
        for teammate in self.get_team(game_state):
            if teammate == self.index:
                continue
            pos = game_state.get_agent_position(teammate)
            if pos is None:
                continue
            teammate_distances.append(self.get_maze_distance(my_pos, pos))

        return min(teammate_distances) if teammate_distances else 0
