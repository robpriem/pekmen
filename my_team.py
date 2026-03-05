import random
import util
from capture_agents import CaptureAgent
from game import Directions
from util import nearest_point

<<<<<<< HEAD

#################
# Team creation #
#################



def create_team(first_index, second_index, is_red,
                first='OffensiveReflexAgent', second='DefensiveMinimaxAgent', num_training=0):
    """
    This function should return a list of two agents that will form the
    team, initialized using firstIndex and secondIndex as their agent
    index numbers.  isRed is True if the red team is being created, and
    will be False if the blue team is being created.

    As a potentially helpful development aid, this function can take
    additional string-valued keyword arguments ("first" and "second" are
    such arguments in the case of this function), which will come from
    the --redOpts and --blueOpts command-line arguments to capture.py.
    For the nightly contest, however, your team will be created without
    any extra arguments, so you should make sure that the default
    behavior is what you want for the nightly contest.

    """
=======
def create_team(first_index, second_index, is_red,
                first='OffensiveMinimaxAgent', second='OffensiveMinimaxAgent', num_training=0):
>>>>>>> 4209c55d9c88d4d824bb4c4f0eeaf0606395a890
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
        return self._minimax_root(game_state, depth=self.search_depth)

    def _minimax_root(self, game_state, depth):
        legal = game_state.get_legal_actions(self.index)
        legal = [a for a in legal if a != Directions.STOP] or legal

        best_a = random.choice(legal)
        best_v = float("-inf")
        alpha, beta = float("-inf"), float("inf")

        for a in legal:
            succ = game_state.generate_successor(self.index, a)
            v = self._alphabeta(succ, depth, self._next_agent(self.index, succ), alpha, beta)
            if v > best_v:
                best_v, best_a = v, a
            alpha = max(alpha, best_v)

        return best_a

    def _alphabeta(self, state, depth, agent_idx, alpha, beta):
        if depth == 0 or state.is_over():
            return self._eval_offense(state)

        ########################################### FIX THIS! ############################################
        st = state.get_agent_state(agent_idx)
        if st is None or st.get_position() is None or st.configuration is None:
            return self._eval_offense(state)

        num_agents = state.get_num_agents()

        # Determine whose turn and next depth.
        next_idx = (agent_idx + 1) % num_agents
        next_depth = depth - 1 if agent_idx == self.index else depth

        actions = state.get_legal_actions(agent_idx)
        if not actions:
            return self._eval_offense(state)

        if agent_idx == self.index:
            # Max node (our agent)
            v = float("-inf")
            for a in actions:
                succ = state.generate_successor(agent_idx, a)
                v = max(v, self._alphabeta(succ, next_depth, next_idx, alpha, beta))
                alpha = max(alpha, v)
                if alpha >= beta:
                    break
            return v

        # Opponents are minimizing
        if agent_idx in self.get_opponents(state):
            v = float("inf")
            for a in actions:
                succ = state.generate_successor(agent_idx, a)
                v = min(v, self._alphabeta(succ, next_depth, next_idx, alpha, beta))
                beta = min(beta, v)
                if alpha >= beta:
                    break
            return v
        else:
            # teammate / others: average outcomes (neutral)
            vals = []
            for a in actions:
                succ = state.generate_successor(agent_idx, a)
                vals.append(self._alphabeta(succ, next_depth, next_idx, alpha, beta))
            return sum(vals) / float(len(vals))

    # ----------------------------
    # Evaluation (Offense Heuristic)
    # ----------------------------

    def _eval_offense(self, game_state):
        #################Offensive parameters###########

        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()

        if my_pos is None:
            return float("-inf")

        Score = self.get_score(game_state)

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
        OffensiveScore += 100 * Score                           #score
        OffensiveScore += 10 * carrying                         # value carrying (future score)
        OffensiveScore += -2.5 * food_dist                       # move toward food
        OffensiveScore += -0.8 * boundary_dist * (carrying > 0)  # when carrying, prefer edging home
        OffensiveScore += -0.3 * endgame_pressure * boundary_dist

        ############################## Defensive parameters #########################
        DefensiveScore = Score

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


<<<<<<< HEAD
    def get_weights(self, game_state, action):
        return {'num_invaders': -1000, 'on_defense': 100, 'invader_distance': -10, 'stop': -100, 'reverse': -2}




MODE_DEFEND = "defend"
MODE_RETURN = "return"
MODE_ATTACK = "attack"

class DefensiveMinimaxAgent(CaptureAgent):
    def register_initial_state(self, game_state):
        super().register_initial_state(game_state)
        self.start = game_state.get_agent_position(self.index)
        self.prev_def_food = self.get_food_you_are_defending(game_state).as_list()
        self.boundary = self._compute_boundary_positions(game_state)
        # Choose a stable "home" on the boundary.
        h = game_state.data.layout.height
        mid_y = h // 2
        boundary_sorted = sorted(self.boundary, key=lambda p: p[1])
        mid_candidates = sorted(boundary_sorted, key=lambda p: abs(p[1] - mid_y))
        self.boundary_home = mid_candidates[0] if len(mid_candidates) > 0 else None

        # Build a small patrol strip around the middle of the map (3 points if available).
        self.boundary_patrol = mid_candidates[:3] if len(mid_candidates) >= 3 else mid_candidates
        # Used to discourage panicky retreats into the start corner.
        self.start_avoid_weight = 0.5
        self.patrol_i = 0

        # Don't let patrol chase a missing-food event too deep into our territory.
        self.max_patrol_chase_dist = 6

        # Missing-food chase should be short-lived (otherwise we get dragged to corners).
        self.missing_chase_target = None
        self.missing_chase_ttl = 0  # in turns

        self.debug = False

    def choose_action(self, game_state):
        my_state = game_state.get_agent_state(self.index)

        # mode selection
        invaders = self._visible_invaders(game_state)
        if my_state.is_pacman:
            mode = MODE_RETURN
        else:
            mode = MODE_DEFEND

        # act
        if mode == MODE_RETURN:
            if self.debug:
                print(f"[DEF {self.index}] MODE=RETURN")
            return self._act_return(game_state)

        # DEFEND:
        # If we're scared, do NOT rush an invader; hold the boundary and keep distance.
        if my_state.scared_timer > 0:
            if self.debug:
                print(f"[DEF {self.index}] MODE=SCARED scared_timer={my_state.scared_timer} invaders={len(invaders)}")
            return self._act_scared(game_state, invaders)

        if len(invaders) > 0:
            # only then: minimax
            if self.debug:
                print(f"[DEF {self.index}] MODE=MINIMAX invaders={len(invaders)}")
            return self._minimax_root(game_state, depth=2)

        # no invaders visible -> patrolling 
        if self.debug:
            print(f"[DEF {self.index}] MODE=PATROL chase_ttl={self.missing_chase_ttl} chase_target={self.missing_chase_target}")
        return self._act_patrol(game_state)

    
    # Return mode
    def _act_return(self, game_state):
        actions = list(game_state.get_legal_actions(self.index))
        my_pos = game_state.get_agent_position(self.index)

        # Prefer returning to a central boundary anchor.
        target = self.boundary_home if self.boundary_home is not None else min(self.boundary, key=lambda b: self.get_maze_distance(my_pos, b))
        cur_start_d = self.get_maze_distance(my_pos, self.start)

        best_a, best_score = None, -10**9
        for a in actions:
            s = game_state.generate_successor(self.index, a)
            pos = s.get_agent_position(self.index)

            # Main objective: get back to boundary anchor.
            score = -10 * self.get_maze_distance(pos, target)

            # Avoid drifting into the start corner while doing so.
            start_d = self.get_maze_distance(pos, self.start)
            score += self.start_avoid_weight * (start_d - cur_start_d)

            if a == Directions.STOP:
                score -= 1

            if score > best_score:
                best_score, best_a = score, a

        return best_a if best_a is not None else Directions.STOP

    # Patrol mode
    def _act_patrol(self, game_state):
        # Detect missing defended food .
        now_food = self.get_food_you_are_defending(game_state).as_list()
        missing = list(set(self.prev_def_food) - set(now_food))
        self.prev_def_food = now_food

        my_pos = game_state.get_agent_position(self.index)

        # Refresh a short-lived chase target when food disappears.
        if len(missing) > 0:
            candidate = min(missing, key=lambda p: self.get_maze_distance(my_pos, p))
            # Only chase if it's not too far away from our midline area.
            if self.get_maze_distance(self.boundary_home, candidate) <= self.max_patrol_chase_dist:
                self.missing_chase_target = candidate
                self.missing_chase_ttl = 6  # chase for at most 6 turns

        # If we have an active chase target, pursue it until TTL expires.
        if self.missing_chase_ttl > 0 and self.missing_chase_target is not None:
            target = self.missing_chase_target
            self.missing_chase_ttl -= 1
        else:
            # Otherwise, patrol a small strip on the boundary near the middle.
            if len(self.boundary_patrol) == 0:
                target = self.boundary_home
            else:
                target = self.boundary_patrol[self.patrol_i % len(self.boundary_patrol)]
                if my_pos == target:
                    self.patrol_i += 1

        if my_pos == target:
            return Directions.STOP
        return self._move_towards(game_state, target)
=======
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
>>>>>>> 4209c55d9c88d4d824bb4c4f0eeaf0606395a890

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

<<<<<<< HEAD
        # Choose a boundary anchor to hold.
        if len(self.boundary_patrol) > 0:
            anchor = self.boundary_patrol[self.patrol_i % len(self.boundary_patrol)]
        else:
            anchor = self.boundary_home

=======
>>>>>>> 4209c55d9c88d4d824bb4c4f0eeaf0606395a890
        # Precompute closest invader distance in current state.
        inv_pos = [i.get_position() for i in invaders if i.get_position() is not None]

        best_a, best_score = None, -10**9
        for a in actions:
            s = game_state.generate_successor(self.index, a)
            pos = s.get_agent_position(self.index)
<<<<<<< HEAD

            # Base: stay near boundary anchor.
            score = -2 * self.get_maze_distance(pos, anchor)
=======
            score = 0
>>>>>>> 4209c55d9c88d4d824bb4c4f0eeaf0606395a890

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

<<<<<<< HEAD
    def _move_towards(self, game_state, target):
        actions = list(game_state.get_legal_actions(self.index))

        # While patrolling/returning, avoid crossing into enemy territory (becoming Pacman)
        # unless STOP is the only option.
        filtered = []
        for a in actions:
            s = game_state.generate_successor(self.index, a)
            st = s.get_agent_state(self.index)
            if not st.is_pacman:
                filtered.append(a)
        if len(filtered) > 0:
            actions = filtered

        best_a, best_d = None, 10**9
        for a in actions:
            s = game_state.generate_successor(self.index, a)
            pos = s.get_agent_position(self.index)
            d = self.get_maze_distance(pos, target)
            # small tie-break: prefer STOP if equal distance (helps holding position)
            if d < best_d or (d == best_d and a == Directions.STOP):
                best_d, best_a = d, a
        return best_a if best_a is not None else Directions.STOP


    # Minimax (alpha-beta)
    def _minimax_root(self, game_state, depth):
        alpha, beta = -10**9, 10**9
        best_val, best_act = -10**9, Directions.STOP
        actions = game_state.get_legal_actions(self.index)

        for a in actions:
            s = game_state.generate_successor(self.index, a)
            val = self._alphabeta(s, depth, self._next_agent(self.index, game_state), alpha, beta)
            if val > best_val:
                best_val, best_act = val, a
            alpha = max(alpha, best_val)
        return best_act

    def _alphabeta(self, state, depth, agent_idx, alpha, beta):
        if depth == 0 or state.is_over():
            return self._eval_defense(state)

        legal = state.get_legal_actions(agent_idx)
        if len(legal) == 0:
            return self._eval_defense(state)

        is_me = (agent_idx == self.index)
        is_enemy = agent_idx in self.get_opponents(state)

        # depth decreases after a full ply
        next_idx = self._next_agent(agent_idx, state)
        next_depth = depth - 1 if is_me else depth

        if is_me:
            v = -10**9
            for a in legal:
                s2 = state.generate_successor(agent_idx, a)
                v = max(v, self._alphabeta(s2, next_depth, next_idx, alpha, beta))
                alpha = max(alpha, v)
                if alpha >= beta:
                    break
            return v

        if is_enemy:
            v = 10**9
            for a in legal:
                s2 = state.generate_successor(agent_idx, a)
                v = min(v, self._alphabeta(s2, next_depth, next_idx, alpha, beta))
                beta = min(beta, v)
                if alpha >= beta:
                    break
            return v

        # teammate or unknown: treat as neutral (or max)
        v = 0
        for a in legal:
            s2 = state.generate_successor(agent_idx, a)
            v += self._alphabeta(s2, next_depth, next_idx, alpha, beta)
        return v / float(len(legal))

    def _eval_defense(self, game_state):
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()

        # If we're scared, being close to invaders is dangerous; prefer distance and holding the boundary.
        if my_state.scared_timer > 0:
            invaders = self._visible_invaders(game_state)
            score = 0
            if my_state.is_pacman:
                score -= 200
            # Hold boundary while scared
            score -= 2 * min(self.get_maze_distance(my_pos, b) for b in self.boundary)
            if len(invaders) > 0:
                d = min(self.get_maze_distance(my_pos, i.get_position()) for i in invaders)
                score += 4 * d
            # Slightly discourage being near the start corner while scared.
            score += self.start_avoid_weight * self.get_maze_distance(my_pos, self.start)
            return score

        score = 0

        # stay defender
        if my_state.is_pacman:
            score -= 200

        invaders = self._visible_invaders(game_state)
        score -= 1000 * len(invaders)

        if len(invaders) > 0:
            d = min(self.get_maze_distance(my_pos, i.get_position()) for i in invaders)
            score -= 10 * d

        if len(invaders) == 0:
            score -= min(self.get_maze_distance(my_pos, b) for b in self.boundary)

        return score

    # Helpers
    def _visible_invaders(self, game_state):
        enemies = [game_state.get_agent_state(i) for i in self.get_opponents(game_state)]
        return [e for e in enemies if e.is_pacman and e.get_position() is not None]

    def _compute_boundary_positions(self, game_state):
        layout = game_state.data.layout
        w, h = layout.width, layout.height
        walls = game_state.get_walls()

        mid_x = (w - 2) // 2
        boundary_x = mid_x if self.red else mid_x + 1

        boundary = []
        for y in range(1, h - 1):
=======
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
>>>>>>> 4209c55d9c88d4d824bb4c4f0eeaf0606395a890
            if not walls[boundary_x][y]:
                boundary.append((boundary_x, y))
        return boundary

    def _next_agent(self, agent_idx, game_state):
<<<<<<< HEAD
        return (agent_idx + 1) % game_state.get_num_agents()
=======
        return (agent_idx + 1) % game_state.get_num_agents()


    # Optional: update your create_team defaults to use the new class:
    # def create_team(first_index, second_index, is_red,
    #                 first='OffensiveMinimaxAgent', second='DefensiveMinimaxAgent', num_training=0):
    #     return [eval(first)(first_index), eval(second)(second_index)]
>>>>>>> 4209c55d9c88d4d824bb4c4f0eeaf0606395a890
