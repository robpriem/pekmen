"""
agents: een AttackAgent en een FlexAgent.

De AttackAgent focust op het ophalen van food bij de tegenstander.
De FlexAgent wisselt dynamisch tussen aanvallen en verdedigen,
afhankelijk van de game state (score, invaders, tijd, ...).
"""

from collections import deque

from capture_agents import CaptureAgent
from game import Directions


def create_team(first_index, second_index, is_red,
                first='AttackAgent', second='FlexAgent', num_training=0):
    return [eval(first)(first_index), eval(second)(second_index)]


# ======================================================================
#  BaseAgent — gedeelde logica voor beide agents
# ======================================================================

class BaseAgent(CaptureAgent):
    """
    Basisklasse met gedeelde functionaliteit:
    - Boundary (grens) berekening
    - Vijand-detectie (invaders, ghosts, scared ghosts)
    - Missing food tracking (om onzichtbare invaders te lokaliseren)
    - Anti-oscillatie mechanisme
    - Generieke actiekeuze via evaluatiefuncties
    """

    def register_initial_state(self, game_state):
        super().register_initial_state(game_state)
        self.start = game_state.get_agent_position(self.index)
        self.boundary = self.compute_boundary(game_state)
        self.last_food_defending = self.get_food_you_are_defending(game_state).as_list()
        self.missing_food = []
        self.recent_positions = deque(maxlen=6)

    #  Boundary berekening 

    def compute_boundary(self, game_state):
        """
        Berekent alle open posities op de rand van onze helft.
        Dit zijn de posities waar we van Pacman terug naar Ghost gaan
        (en dus onze opgehaalde food scoren).
        """
        walls = game_state.get_walls()
        width, height = walls.width, walls.height
        # Rode kant: grens op x = width/2 - 1, blauwe kant: x = width/2
        x = (width // 2 - 1) if self.red else (width // 2)
        return [(x, y) for y in range(height) if not walls[x][y]]

    def boundary_distance(self, pos):
        """Kortste maze-afstand van pos tot de dichtstbijzijnde boundary-positie."""
        if not pos or not self.boundary:
            return 0
        return min(self.get_maze_distance(pos, b) for b in self.boundary)

    #  Vijand-detectie 

    def get_visible_invaders(self, game_state):
        """
        Geeft zichtbare vijanden die op onze helft zijn (zij zijn Pacman).
        Returnt een lijst van (index, positie) tuples.
        """
        result = []
        for i in self.get_opponents(game_state):
            state = game_state.get_agent_state(i)
            pos = state.get_position()
            if pos and state.is_pacman:
                result.append((i, pos))
        return result

    def get_visible_ghosts(self, game_state):
        """
        Geeft zichtbare vijandelijke ghosts die ons kunnen eten (niet scared).
        """
        result = []
        for i in self.get_opponents(game_state):
            state = game_state.get_agent_state(i)
            pos = state.get_position()
            if pos and not state.is_pacman and state.scared_timer <= 0:
                result.append((i, pos))
        return result

    def get_visible_scared_ghosts(self, game_state):
        """
        Geeft zichtbare scared ghosts die wij kunnen opeten.
        """
        result = []
        for i in self.get_opponents(game_state):
            state = game_state.get_agent_state(i)
            pos = state.get_position()
            if pos and not state.is_pacman and state.scared_timer > 0:
                result.append((i, pos, state.scared_timer))
        return result

    def get_closest_noisy_enemy_distance(self, game_state):
        """
        Geeft de laagste noisy distance tot een vijand.
        Noisy distances zijn altijd beschikbaar maar hebben ruis van +-6.
        Nuttig als grove indicator wanneer vijanden niet zichtbaar zijn.
        """
        dists = game_state.get_agent_distances()
        if dists is None:
            return None
        vals = [dists[i] for i in self.get_opponents(game_state)]
        return min(vals) if vals else None

    #  Food tracking 

    def update_missing_food(self, game_state):
        """
        Vergelijkt de food die we verdedigen met vorige beurt.
        Verdwenen food betekent dus  een invader die daar geweest is.
        """
        current = self.get_food_you_are_defending(game_state).as_list()
        self.missing_food = [f for f in self.last_food_defending if f not in current]
        self.last_food_defending = current

    #  Andere helpers 

    def get_teammate_position(self, game_state):
        """Geeft de positie van onze teammate, of None als die niet zichtbaar is."""
        for i in self.get_team(game_state):
            if i != self.index:
                pos = game_state.get_agent_position(i)
                if pos:
                    return pos
        return None

    def pick_best_action(self, game_state, eval_fn):
        """
        Evalueert elke legale actie met de gegeven evaluatiefunctie
        en kiest de actie met de hoogste score. Past ook straffen
        toe voor stilstaan, omkeren en herhaalde posities (anti-oscillatie).
        """
        actions = game_state.get_legal_actions(self.index)
        my_state = game_state.get_agent_state(self.index)

        # Bepaal de omgekeerde richting
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

            # Straf voor direct omkeren
            if action == reverse:
                score -= 8

            # Straf voor herhaalde posities (anti-oscillatie)
            succ_pos = successor.get_agent_position(self.index)
            if succ_pos:
                repeats = self.recent_positions.count(succ_pos)
                score -= 11 * repeats

            if score > best_score:
                best_score = score
                best_action = action

        return best_action


# ======================================================================
#  AttackAgent
# ======================================================================

class AttackAgent(BaseAgent):
    """
     haalt food op bij de tegenstander en brengt
    het terug naar onze helft. Ontwijkt ghosts, jaagt op scared ghosts,
    en schakelt kort over naar verdediging als een invader heel dichtbij is.
    """

    def choose_action(self, game_state):
        self.update_missing_food(game_state)
        my_pos = game_state.get_agent_position(self.index)
        if my_pos:
            self.recent_positions.append(my_pos)

        # Als we op eigen helft zijn en een invader is binnen 3 stappen,
        # kort verdedigen voordat we weer aanvallen
        if not game_state.get_agent_state(self.index).is_pacman:
            invaders = self.get_visible_invaders(game_state)
            if invaders and my_pos:
                closest_inv = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
                if closest_inv <= 3:
                    return self.pick_best_action(game_state, self.evaluate_defense)

        return self.pick_best_action(game_state, self.evaluate_offense)

    def evaluate_offense(self, game_state):
        """
        Evaluatiefunctie voor aanvallen. Weegt af:
        - Game score (punten scoren is het belangrijkst)
        - Afstand tot food (dichterbij = beter)
        - Carrying druk (hoe meer food je draagt, hoe meer je terug wilt)
        - Ghost avoidance (dichtbij = grote straf)
        - Scared ghost achtervolging
        - Capsule gebruik
        - Eindspel druk 
        - Team spacing (niet te dicht bij teammate)
        """
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        carrying = my_state.num_carrying
        food = self.get_food(game_state).as_list()
        ghosts = self.get_visible_ghosts(game_state)
        scared_ghosts = self.get_visible_scared_ghosts(game_state)
        capsules = self.get_capsules(game_state)
        boundary_dist = self.boundary_distance(my_pos)
        time_left = game_state.data.timeleft or 1200
        game_score = self.get_score(game_state)

        # Punten scoren is het einddoel
        score += 200 * game_score

        # Ga naar de dichtstbijzijnde food, straf overgebleven food
        if food:
            closest_food = min(self.get_maze_distance(my_pos, f) for f in food)
            score -= 2 * closest_food
        score -= 4 * len(food)

        # Hoe meer food je draagt, hoe belangrijker het is om terug te keren
        score += 10 * carrying
        if carrying > 0:
            score -= 3 * carrying * boundary_dist
        if carrying >= 5:
            score -= 10 * boundary_dist
        if len(food) <= 2 and carrying > 0:
            score -= 50 * boundary_dist

        # Vermijd ghosts, strenger naarmate dichterbij
        ghost_nearby = False
        for _, ghost_pos in ghosts:
            dist = self.get_maze_distance(my_pos, ghost_pos)
            if dist <= 1:
                score -= 500
                ghost_nearby = True
            elif dist <= 2:
                score -= 150
                ghost_nearby = True
            elif dist <= 3:
                score -= 40
                ghost_nearby = True
            elif dist <= 5:
                score -= 10

        # Ghost dichtbij terwijl we food dragen: extra druk om terug te keren
        if ghost_nearby and carrying > 0:
            score -= 20 * boundary_dist

        # Jaag op scared ghosts,  enkel  als we ze op tijd bereiken
        for _, scared_pos, timer in scared_ghosts:
            dist = self.get_maze_distance(my_pos, scared_pos)
            if timer > dist:
                score += 60 - 4 * dist

        # Capsules pakken als er een ghost dichtbij is
        if capsules and ghosts:
            closest_capsule = min(self.get_maze_distance(my_pos, c) for c in capsules)
            score -= 2 * closest_capsule

        # Eindspel: bij weinig tijd extra druk om terug te keren
        if time_left < 100:
            score -= 15 * boundary_dist
        elif time_left < 200 and carrying > 0:
            score -= 8 * boundary_dist

        # Niet te dicht bij teammate 
        teammate_pos = self.get_teammate_position(game_state)
        if teammate_pos:
            team_dist = self.get_maze_distance(my_pos, teammate_pos)
            if team_dist <= 1:
                score -= 40
            elif team_dist <= 3:
                score -= 15

        return score

    def evaluate_defense(self, game_state):
        """
         korte defensieve evaluatie, alleen gebruik als een invader
        heel dichtbij is terwijl wij op eigen helft staan.
        """
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        invaders = self.get_visible_invaders(game_state)

        # Blijf op eigen helft
        if my_state.is_pacman:
            score -= 80

        # Jaag op de dichtstbijzijnde invader
        if invaders:
            closest = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
            score -= 13 * closest

        return score


# ======================================================================
#  FlexAgent — flexibele verdediger/aanvaller
# ======================================================================

class FlexAgent(BaseAgent):
    """
    Flexibele agent die elke beurt beslist of hij verdedigt of aanvalt.
    Verdedigt als we voorstaan, als er invaders zijn, of als
    een vijand dichtbij lijkt (noisy distance). Valt aan als we achter
    staan en de kust veilig is.
    """

    def choose_action(self, game_state):
        self.update_missing_food(game_state)
        my_pos = game_state.get_agent_position(self.index)
        if my_pos:
            self.recent_positions.append(my_pos)

        if self.should_defend(game_state):
            return self.pick_best_action(game_state, self.evaluate_defense)
        else:
            return self.pick_best_action(game_state, self.evaluate_offense)

    def should_defend(self, game_state):
        """
        Beslist of de FlexAgent moet verdedigen of aanvallen.
        Geeft True terug als verdedigen de betere keuze is.
        """
        my_state = game_state.get_agent_state(self.index)
        invaders = self.get_visible_invaders(game_state)
        game_score = self.get_score(game_state)

        # Alle vijanden zijn scared: geen defense nodig, aanvallen
        all_scared = all(
            game_state.get_agent_state(i).scared_timer > 0
            for i in self.get_opponents(game_state)
        )
        if all_scared:
            return False

        # Als we op vijandelijk terrein zijn met veel food, eerst terugbrengen
        if my_state.is_pacman and my_state.num_carrying >= 4:
            return False

        # Zichtbare invaders: altijd verdedigen
        if invaders:
            return True

        # Food is verdwenen: invader ergens op onze helft
        if self.missing_food:
            return True

        # Noisy distance
        noisy_dist = self.get_closest_noisy_enemy_distance(game_state)
        if noisy_dist is not None and noisy_dist <= 6:
            return True

        # winnende: bescherm de voorsprong
        if game_score > 0:
            return True

        # Score gelijk en we zijn op eigen helft: blijf verdedigen
        if game_score == 0 and not my_state.is_pacman:
            return True

        return False

    def evaluate_defense(self, game_state):
        """
        Evaluatiefunctie voor verdedigen. Drie scenario's:
        1. Wij zijn scared: volg invader op afstand 
        2. Invaders zichtbaar: jagen
        3. Niks: patrouilleer bij de meest kwetsbare food
        """
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        invaders = self.get_visible_invaders(game_state)

        # Straf voor op de verkeerde helft staan
        if my_state.is_pacman:
            score -= 100

        # Als wij scared zijn: hou afstand van invaders 
        if my_state.scared_timer > 0 and invaders:
            closest = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
            if closest <= 1:
                score -= 200  
            elif closest <= 4:
                score += 5 * closest  
            else:
                score -= closest  
            return score

        # Jaag  op zichtbare invaders
        if invaders:
            closest = min(self.get_maze_distance(my_pos, p) for _, p in invaders)
            score -= 15 * closest
            score -= 100 * len(invaders)

        # Food verdwenen: ga naar waar het verdween (invader was daar)
        elif self.missing_food:
            closest_missing = min(self.get_maze_distance(my_pos, f) for f in self.missing_food)
            score -= 5 * closest_missing

        # Niks: patrouilleer bij de meest kwetsbare food
        # food die het dichtst bij de grens ligt, want daar komt de vijand binnen
        else:
            our_food = self.get_food_you_are_defending(game_state).as_list()
            if our_food and self.boundary:
                most_vulnerable = None
                shortest_dist = float('inf')
                for food_pos in our_food:
                    dist_to_boundary = min(
                        self.get_maze_distance(food_pos, b) for b in self.boundary
                    )
                    if dist_to_boundary < shortest_dist:
                        shortest_dist = dist_to_boundary
                        most_vulnerable = food_pos
                score -= 2 * self.get_maze_distance(my_pos, most_vulnerable)
            score -= self.boundary_distance(my_pos)

        return score

    def evaluate_offense(self, game_state):
        """
        Evaluatiefunctie voor aanvallen. Iets voorzichtiger dan de AttackAgent:
        de FlexAgent keert sneller terug en weegt
        de boundary-afstand zwaarder wanneer hij food draagt.
        """
        my_state = game_state.get_agent_state(self.index)
        my_pos = my_state.get_position()
        if not my_pos:
            return 0

        score = 0.0
        carrying = my_state.num_carrying
        food = self.get_food(game_state).as_list()
        ghosts = self.get_visible_ghosts(game_state)
        scared_ghosts = self.get_visible_scared_ghosts(game_state)
        capsules = self.get_capsules(game_state)
        boundary_dist = self.boundary_distance(my_pos)
        game_score = self.get_score(game_state)

        score += 200 * game_score

        if food:
            closest_food = min(self.get_maze_distance(my_pos, f) for f in food)
            score -= 2 * closest_food
        score -= 4 * len(food)

        # Carrying: FlexAgent keert snleller terug dan AttackAgent
        score += 10 * carrying
        if carrying > 0:
            score -= 4 * carrying * boundary_dist
        if carrying >= 3:
            score -= 12 * boundary_dist
        if len(food) <= 2 and carrying > 0:
            score -= 50 * boundary_dist

        # Ghost avoidance
        for _, ghost_pos in ghosts:
            dist = self.get_maze_distance(my_pos, ghost_pos)
            if dist <= 1:
                score -= 500
            elif dist <= 2:
                score -= 150
            elif dist <= 3:
                score -= 40
            elif dist <= 5:
                score -= 10

        # Scared ghosts achtervolgen als haalbaar is
        for _, scared_pos, timer in scared_ghosts:
            dist = self.get_maze_distance(my_pos, scared_pos)
            if timer > dist:
                score += 60 - 4 * dist

        # Capsules pakken als ghost dichtbij
        if capsules and ghosts:
            closest_capsule = min(self.get_maze_distance(my_pos, c) for c in capsules)
            score -= 2 * closest_capsule

        # Team spacing
        teammate_pos = self.get_teammate_position(game_state)
        if teammate_pos:
            team_dist = self.get_maze_distance(my_pos, teammate_pos)
            if team_dist <= 1:
                score -= 40
            elif team_dist <= 3:
                score -= 15

        return score
