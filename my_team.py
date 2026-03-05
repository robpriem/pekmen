import random
import util
from capture_agents import CaptureAgent
from game import Directions
from util import nearest_point

def create_team(first_index, second_index, is_red,
                first='OffensiveMinimaxAgent', second='OffensiveMinimaxAgent', num_training=0):
    return [eval(first)(first_index), eval(second)(second_index)]


class OffensiveMinimaxAgent(CaptureAgent):
    def register_initial_state(self, game_state):
        super().register_initial_state(game_state)
        self.start = game_state.get_agent_position(self.index)
        self.boundary = self._compute_boundary_positions(game_state)
        self.boundary_home = min(
            self.boundary,
            key=lambda p: abs(p[1] - (game_state.data.layout.height // 2))
        )
        self.search_depth = 2
        self.return_food_threshold = 5
        self.danger_dist = 3
        self.endgame_return_buffer = 35

    def choose_action(self, game_state):
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()

        if my_pos is None:
            return Directions.STOP

        visible_defenders = self._visible_defenders(game_state)
        threatened = False

        if visible_defenders:
            dmin = min(self.get_maze_distance(my_pos, e.get_position()) for e in visible_defenders)
            threatened = (dmin <= self.danger_dist)

        time_left = getattr(game_state.data, "timeleft", None)
        carrying = my_state.num_carrying

        invaders = self._visible_invaders(game_state)

        ############################## Act scared ###############
        if my_state.scared_timer > 0:
            return self._act_scared(game_state, invaders)

        ############################### Return ###################
        should_return = (
                carrying >= self.return_food_threshold
                or threatened
                or (time_left is not None and time_left < self.endgame_return_buffer)
        )
        if should_return:
            return self._move_towards(game_state, self.boundary_home)

        ##################################### Mini-Max ###############@#####################
        return self._alphabeta(game_state, self.search_depth, 0, float("-inf"), float("+inf"))

    def _alphabeta(self, state, depth, agent_idx, alpha, beta):
        # Terminal
        if depth == 0 or state.is_over():
            return self._eval_offense(state)

        num_agents = state.get_num_agents()

        # Compute next turn info FIRST (so we can "skip" safely if needed)
        next_idx = (agent_idx + 1) % num_agents

        # Decrement depth only when the turn order wraps back to us
        next_depth = depth - 1 if next_idx == self.index else depth

        # If we can't simulate this agent (e.g., unseen enemy => position None), skip their turn
        st = state.get_agent_state(agent_idx)
        if st is None or st.get_position() is None or getattr(st, "configuration", None) is None:
            return self._alphabeta(state, next_depth, next_idx, alpha, beta)

        actions = state.get_legal_actions(agent_idx)
        if not actions:
            return self._alphabeta(state, next_depth, next_idx, alpha, beta)

        # Optional: avoid STOP everywhere to reduce loops

        actions = [a for a in actions if a != Directions.STOP] or actions

        # Team = MAX, Opponents = MIN (pure minimax => alpha-beta is valid)
        if agent_idx in self.get_team(state):  # includes self.index
            v = float("-inf")
            for a in actions:
                succ = state.generate_successor(agent_idx, a)
                v = max(v, self._alphabeta(succ, next_depth, next_idx, alpha, beta))
                alpha = max(alpha, v)
                if alpha >= beta:
                    break
            return v
        else:
           v = float("inf")
           for a in actions:
            succ = state.generate_successor(agent_idx, a)
            v = min(v, self._alphabeta(succ, next_depth, next_idx, alpha, beta))
            beta = min(beta, v)
            if alpha >= beta:
                break
            return v

    # ----------------------------
    # Evaluation (Offense Heuristic)
    # ----------------------------

    def _eval_offense(self, game_state):
        ################# Offensive parameters ###########

        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()

        if my_pos is None:
            return float("-inf")

        score = self.get_score(game_state)

        # Food
        food = self.get_food(game_state).as_list()
        food_dist = min((self.get_maze_distance(my_pos, f) for f in food), default=0)

        # Carrying incentive
        carrying = my_state.num_carrying

        # Return incentive grows with carrying and with time pressure
        boundary_dist = min(self.get_maze_distance(my_pos, b) for b in self.boundary) if self.boundary else 0

        time_left = getattr(game_state.data, "timeleft", None)
        endgame_pressure = 0

        if time_left is not None:
            # small bump as time gets low
            endgame_pressure = max(0, (self.endgame_return_buffer - time_left))

        # Weighted sum offensive parameters
        OffensiveScore = 0.0
        OffensiveScore += 100 * score                           #score
        OffensiveScore += 10 * carrying                         # value carrying (future score)
        OffensiveScore += -2.5 * food_dist                       # move toward food
        OffensiveScore += -0.8 * boundary_dist * (carrying > 0)  # when carrying, prefer edging home
        OffensiveScore += -0.3 * endgame_pressure * boundary_dist

        ############################## Defensive parameters #########################
        DefensiveScore = score

        # Visible defenders (ghosts) danger
        defenders = self._visible_defenders(game_state)
        danger_pen = 0

        if defenders:
            dmin = min(self.get_maze_distance(my_pos, d.get_position()) for d in defenders)

            #If we can be eaten (they're not scared), avoid strongly when close

            if any(d.scared_timer == 0 for d in defenders):
                if dmin <= 2:
                    danger_pen -= 2000
                else:
                    danger_pen -= 200 / float(dmin)
            else:
                # If defenders are scared, we can be bolder
                danger_pen += 20 / float(max(1, dmin))

        DefensiveScore += danger_pen

        #aantal invaders
        invaders = self._visible_invaders(game_state)
        DefensiveScore -= 100 * len(invaders)

        #als alle tegenstanders dood zijn
        if len(invaders) == 0:
            DefensiveScore -= min(self.get_maze_distance(my_pos, b) for b in self.boundary)

        #minimum afstand tot invaders
        if len(invaders) > 0:
            d = min(self.get_maze_distance(my_pos, i.get_position()) for i in invaders)
            DefensiveScore = 10 * d

        return (0.75 * OffensiveScore + 0.25 * DefensiveScore)


    def _move_towards(self, game_state, target):
        """Greedy step toward a target; filters moves that are obviously terrible."""
        actions = game_state.get_legal_actions(self.index)
        if not actions:
            return Directions.STOP

        # Prefer not to STOP if we can move
        non_stop = [a for a in actions if a != Directions.STOP]
        if non_stop:
            actions = non_stop

        best = None
        best_d = float("inf")
        for a in actions:
            succ = game_state.generate_successor(self.index, a)
            pos = succ.get_agent_state(self.index).get_position()
            if pos is None:
                continue
            d = self.get_maze_distance(pos, target)
            if d < best_d:
                best_d, best = d, a

        return best if best is not None else random.choice(actions)

    def _act_scared(self, game_state, invaders):
        my_pos = game_state.get_agent_position(self.index)
        cur_start_d = self.get_maze_distance(my_pos, self.start)
        actions = list(game_state.get_legal_actions(self.index))

        # Avoid crossing into enemy territory while scared.
        safe_actions = []
        for a in actions:
            s = game_state.generate_successor(self.index, a)
            if not s.get_agent_state(self.index).is_pacman:
                safe_actions.append(a)
        if len(safe_actions) > 0:
            actions = safe_actions

        # Precompute closest invader distance in current state.
        inv_pos = [i.get_position() for i in invaders if i.get_position() is not None]

        best_a, best_score = None, -10**9
        for a in actions:
            s = game_state.generate_successor(self.index, a)
            pos = s.get_agent_position(self.index)
            score = 0

            # If invaders visible: prefer to keep distance while staying near midline.
            if len(inv_pos) > 0:
                d = min(self.get_maze_distance(pos, p) for p in inv_pos)
                score += 4 * d

            # Discourage moving toward start corner while scared.
            start_d = self.get_maze_distance(pos, self.start)
            score += self.start_avoid_weight * (start_d - cur_start_d)

            # Mild penalty for stopping unless it is genuinely best.
            if a == Directions.STOP:
                score -= 1

            if score > best_score:
                best_score, best_a = score, a

        return best_a if best_a is not None else Directions.STOP

    # ----------------------------
    # Helpers
    # ----------------------------

    def _visible_defenders(self, game_state):
        """Visible opponents that are ghosts (i.e., defenders), with known positions."""
        res = []
        for i in self.get_opponents(game_state):
            st = game_state.get_agent_state(i)
            pos = st.get_position()
            if pos is None:
                continue
            # A defender is a ghost: not pacman (on their home side)
            if not st.is_pacman:
                res.append(st)
        return res

    def _visible_invaders(self, game_state):
        """Visible opponents that are Pacman (invading our side), with known positions."""
        res = []
        for i in self.get_opponents(game_state):
            st = game_state.get_agent_state(i)
            if st.get_position() is None:
                continue
            if st.is_pacman:
                res.append(st)
        return res

    def _compute_boundary_positions(self, game_state):
        walls = game_state.get_walls()
        width = game_state.data.layout.width
        height = game_state.data.layout.height

        # Same convention as your defender: boundary x differs for red/blue
        if self.red:
            boundary_x = (width // 2) - 1
        else:
            boundary_x = (width // 2)

        boundary = []
        for y in range(height):
            if not walls[boundary_x][y]:
                boundary.append((boundary_x, y))
        return boundary

    def _next_agent(self, agent_idx, game_state):
        return (agent_idx + 1) % game_state.get_num_agents()


    # Optional: update your create_team defaults to use the new class:
    # def create_team(first_index, second_index, is_red,
    #                 first='OffensiveMinimaxAgent', second='DefensiveMinimaxAgent', num_training=0):
    #     return [eval(first)(first_index), eval(second)(second_index)]