from collections import deque

from capture_agents import CaptureAgent
from game import Directions


def create_team(first_index, second_index, is_red,
                first='AttackAgent', second='FlexAgent', num_training=0):
    return [eval(first)(first_index), eval(second)(second_index)]


###############################
# Basis Agent,gedeelde logica #
###############################

class BaseAgent(CaptureAgent):

    def register_initial_state(self, game_state):
        super().register_initial_state(game_state)
        self.start = game_state.get_agent_position(self.index)
        self.boundary = self.get_boundary(game_state)
        self.last_food_defending = self.get_food_you_are_defending(game_state).as_list()
        self.missing_food = []
        self.recent_positions = deque(maxlen=6)

    #boundary berekening 

    def get_boundary(self, game_state):
        walls = game_state.get_walls()
        w, h = walls.width, walls.height
        x = (w // 2 - 1) if self.red else (w // 2)
        return [(x, y) for y in range(h) if not walls[x][y]]

    def boundary_dist(self, pos):
        if not pos or not self.boundary:
            return 0
        return min(self.get_maze_distance(pos, b) for b in self.boundary)

    #Helpers 

    def get_invaders(self, game_state):
        result = []
        for i in self.get_opponents(game_state):
            s = game_state.get_agent_state(i)
            p = s.get_position()
            if p and s.is_pacman:
                result.append((i, p))
        return result

    def get_ghosts(self, game_state):
        result = []
        for i in self.get_opponents(game_state):
            s = game_state.get_agent_state(i)
            p = s.get_position()
            if p and not s.is_pacman and s.scared_timer <= 0:
                result.append((i, p))
        return result

    def get_scared_ghosts(self, game_state):
        result = []
        for i in self.get_opponents(game_state):
            s = game_state.get_agent_state(i)
            p = s.get_position()
            if p and not s.is_pacman and s.scared_timer > 0:
                result.append((i, p, s.scared_timer))
        return result

    def closest_noisy_enemy(self, game_state):
        dists = game_state.get_agent_distances()
        if dists is None:
            return None
        vals = [dists[i] for i in self.get_opponents(game_state)]
        return min(vals) if vals else None


    def update_missing_food(self, game_state):
        #Checken wazr er een invader is geweest door opgegeten food.
        current = self.get_food_you_are_defending(game_state).as_list()
        self.missing_food = [f for f in self.last_food_defending if f not in current]
        self.last_food_defending = current

    def teammate_pos(self, game_state):
        for i in self.get_team(game_state):
            if i != self.index:
                t = game_state.get_agent_position(i)
                if t:
                    return t
        return None

    def pick_best_action(self, game_state, eval_fn):
        #Kies de actie met de hoogste evaluatiescore.
        actions = game_state.get_legal_actions(self.index)
        my_state = game_state.get_agent_state(self.index)

        #Bepaal de omgekeerde richting om oscillatie te straffen
        reverse = None
        if my_state and my_state.configuration:
            reverse = Directions.REVERSE.get(my_state.configuration.direction)

        best_score = float('-inf')
        best_action = Directions.STOP

        for action in actions:
            successor = game_state.generate_successor(self.index, action)
            score = eval_fn(successor)

            # Stilstaan is bijna nooit nuttig
            if action == Directions.STOP:
                score -= 15

            
            if action == reverse:
                score -= 8

            # anti-oscillatie
            succ_pos = successor.get_agent_position(self.index)
            if succ_pos:
                repeats = self.recent_positions.count(succ_pos)
                score -= 11 * repeats

            if score > best_score:
                best_score = score
                best_action = action

        return best_action


#################
#  AttackAgent  #
#################
class AttackAgent(BaseAgent):
    
    #Haalt food op bij de tegenstander en brengt het terug.
    #Ontwijkt ghosts, jaagt op scared ghosts, en helpt 
    #met verdedigen als een invader erg dichtbij is.

    def choose_action(self, game_state):
        self.update_missing_food(game_state)
        my_pos = game_state.get_agent_position(self.index)
        if my_pos:
            self.recent_positions.append(my_pos)

        if not game_state.get_agent_state(self.index).is_pacman:
            invaders = self.get_invaders(game_state)
            if invaders and my_pos:
                closest_inv = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
                if closest_inv <= 3:
                    return self.pick_best_action(game_state, self.eval_defense)

        return self.pick_best_action(game_state, self.eval_offense)
    # Als een invader dichtbij is en wij zijn op eigen veld, kort verdedigen anders ga je aanvallen.


    def eval_offense(self, game_state):
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        carrying = my_state.num_carrying
        food = self.get_food(game_state).as_list()
        ghosts = self.get_ghosts(game_state)
        scared = self.get_scared_ghosts(game_state)
        capsules = self.get_capsules(game_state)
        bdist = self.boundary_dist(my_pos)
        time_left = game_state.data.timeleft or 1200
        game_score = self.get_score(game_state)

        # Scoren telt het meest, geeft voorkeur aan actie die effectief ook punten scoort.
        score += 200 * game_score

        # Food ophalen, hoe dichter bij een food hoe beter , hoe meer food er nog ligt , hoe slechter.
        if food:
            closest_food = min(self.get_maze_distance(my_pos, f) for f in food)
            score -= 2 * closest_food
        score -= 4 * len(food)

        # Carrying, breng food terug naar eigen kant.
        score += 10 * carrying
        if carrying > 0:
            score -= 3 * carrying * bdist
        if carrying >= 5:
            score -= 10 * bdist
        # Bijna geen food meer over, dan snel terrugkeren.
        if len(food) <= 2 and carrying > 0:
            score -= 50 * bdist

        # Ghosts vermijden.
        ghost_nearby = False
        for _, ghostpos in ghosts:
            d = self.get_maze_distance(my_pos, ghostpos)
            if d <= 1:
                score -= 500
                ghost_nearby = True
            elif d <= 2:
                score -= 150
                ghost_nearby = True
            elif d <= 3:
                score -= 40
                ghost_nearby = True
            elif d <= 5:
                score -= 10

        # Ghost dichtbij en food bij ons -> extra druk om terug te keren
        if ghost_nearby and carrying > 0:
            score -= 20 * bdist

        # Scared ghost doden als je er op tijd geraakt, anders niet achternagaan
        for _, scaredpos, timer in scared:
            d = self.get_maze_distance(my_pos, scaredpos)
            if timer > d:
                score += 60 - 4 * d

        # Capsules pakken als er een ghost dichtbij is
        if capsules and ghosts:
            closest_cap = min(self.get_maze_distance(my_pos, c) for c in capsules)
            score -= 2 * closest_cap

        # als er ni veel tijd meer is, terugkeren. iets meer tijd en je hebt nog food bij dan meer druk om terug te brengen.
        if time_left < 100:
            score -= 15 * bdist
        elif time_left < 200 and carrying > 0:
            score -= 8 * bdist

        #teammates niet te dicht bij elkaar 
        tp = self.teammate_pos(game_state)
        if tp:
            td = self.get_maze_distance(my_pos, tp)
            if td <= 1:
                score -= 40
            elif td <= 3:
                score -= 15

        return score

    def eval_defense(self, game_state):
        #verdedigen als er een enemy dichtbij is.
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        invaders = self.get_invaders(game_state)

        # op eigen helft blijven.
        if my_state.is_pacman:
            score -= 80

        #invaders neerhalen.
        if invaders:
            closest = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
            score -= 13 * closest

        return score


##############
# FlexAgent #
##############

class FlexAgent(BaseAgent):
   #Gaat verdedigen als er invaders zijn of als we een voorsprong hebben op de andere. Valt aan als er geen invaders zijn.

    def choose_action(self, game_state):
        self.update_missing_food(game_state)
        my_pos = game_state.get_agent_position(self.index)
        if my_pos:
            self.recent_positions.append(my_pos)

        if self.should_defend(game_state):
            return self.pick_best_action(game_state, self.eval_defense)
        else:
            return self.pick_best_action(game_state, self.eval_offense)

    def should_defend(self, game_state):
        my_state = game_state.get_agent_state(self.index)
        invaders = self.get_invaders(game_state)
        game_score = self.get_score(game_state)
        time_left = game_state.data.timeleft or 1200

        # als alle enemys scared zijn, dan aanvallen.
        all_scared = all(
            game_state.get_agent_state(i).scared_timer > 0
            for i in self.get_opponents(game_state)
        )
        if all_scared:
            return False

        if my_state.is_pacman and my_state.num_carrying >= 4:
            return False

        if invaders:
            return True

        if self.missing_food:
            return True

        noisy_distance = self.closest_noisy_enemy(game_state)
        if noisy_distance is not None and noisy_distance <= 6:
            return True

        if game_score > 0:
            return True

        if game_score == 0 and not my_state.is_pacman:
            return True

        return False

    def eval_defense(self, game_state):
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        invaders = self.get_invaders(game_state)

        # Verkeerde kant.
        if my_state.is_pacman:
            score -= 100

        #op afstand blijven bij scared en invaders.
        if my_state.scared_timer > 0 and invaders:
            closest = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
            if closest <= 1:
                score -= 200 
            elif closest <= 4:
                score += 5 * closest  
            else:
                score -= closest  
            return score

        if invaders:
            closest = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
            score -= 15 * closest
            score -= 100 * len(invaders)


        elif self.missing_food:
            closest_missing = min(self.get_maze_distance(my_pos, f) for f in self.missing_food)
            score -= 5 * closest_missing

#als er niks aan de hand is, naar food gaan die dichtst bij de grens ligt.
        else:
            our_food = self.get_food_you_are_defending(game_state).as_list()
            if our_food and self.boundary:
                closest_to_boundary = None
                shortest_distance = float('inf')
                for food in our_food:
                    distance_to_boundary = min(self.get_maze_distance(food, b) for b in self.boundary)
                    if distance_to_boundary < shortest_distance:
                        shortest_distance = distance_to_boundary
                        closest_to_boundary = food
                score -= 2 * self.get_maze_distance(my_pos, closest_to_boundary)
            score -= self.boundary_dist(my_pos)

        return score

    def eval_offense(self, game_state):
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        carrying = my_state.num_carrying
        food = self.get_food(game_state).as_list()
        ghosts = self.get_ghosts(game_state)
        scared = self.get_scared_ghosts(game_state)
        capsules = self.get_capsules(game_state)
        bdist = self.boundary_dist(my_pos)
        game_score = self.get_score(game_state)

        score += 200 * game_score

        if food:
            closest_food = min(self.get_maze_distance(my_pos, f) for f in food)
            score -= 2 * closest_food
        score -= 4 * len(food)


        score += 10 * carrying
        if carrying > 0:
            score -= 4 * carrying * bdist
        if carrying >= 3:
            score -= 12 * bdist
        if len(food) <= 2 and carrying > 0:
            score -= 50 * bdist


        for _, ghostpos in ghosts:
            d = self.get_maze_distance(my_pos, ghostpos)
            if d <= 1:
                score -= 500
            elif d <= 2:
                score -= 150
            elif d <= 3:
                score -= 40
            elif d <= 5:
                score -= 10

        for _, scaredpos, timer in scared:
            d = self.get_maze_distance(my_pos, scaredpos)
            if timer > d:
                score += 60 - 4 * d

        if capsules and ghosts:
            closest_cap = min(self.get_maze_distance(my_pos, c) for c in capsules)
            score -= 2 * closest_cap

        tp = self.teammate_pos(game_state)
        if tp:
            td = self.get_maze_distance(my_pos, tp)
            if td <= 1:
                score -= 40
            elif td <= 3:
                score -= 15

        return score
