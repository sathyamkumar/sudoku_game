import json
from channels.generic.websocket import AsyncWebsocketConsumer
import random
import asyncio

class GameConsumer(AsyncWebsocketConsumer):
    # Class variables to store rooms, boards, solutions and player states
    rooms = {}
    game_boards = {}  # Store initial game boards
    solved_boards = {}  # Store solutions
    player_states = {}  # Store individual player states
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_name = None
        self.room_group_name = None
        self.player_id = None

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'game_{self.room_name}'
        self.player_id = self.channel_name

        # Initialize room if it doesn't exist
        if self.room_name not in self.rooms:
            self.rooms[self.room_name] = set()
            self.game_boards[self.room_name] = None
            self.solved_boards[self.room_name] = None
            self.player_states[self.room_name] = {}

        # Check if room is full (2 players maximum)
        if len(self.rooms[self.room_name]) >= 2:
            await self.close()
            return

        # Initialize player state with a copy of the game board if it exists
        initial_board = [[0 for _ in range(9)] for _ in range(9)]
        if self.game_boards[self.room_name]:
            initial_board = [row[:] for row in self.game_boards[self.room_name]]
        
        self.player_states[self.room_name][self.player_id] = {
            'board': initial_board,
            'chances': 3,
            'is_eliminated': False
        }

        # Add player to room
        self.rooms[self.room_name].add(self.player_id)

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()

        # If this is the second player, generate the board
        if len(self.rooms[self.room_name]) == 2:
            await self.initial_board_setup()
        # If board exists, send it to the new player
        elif self.game_boards[self.room_name]:
            await self.send(text_data=json.dumps({
                'type': 'board_update',
                'board': self.player_states[self.room_name][self.player_id]['board'],
                'chances': self.player_states[self.room_name][self.player_id]['chances']
            }))

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'player_update',
                'count': len(self.rooms[self.room_name])
            }
        )

    async def disconnect(self, close_code):
        if self.room_name in self.rooms:
            self.rooms[self.room_name].discard(self.player_id)
            if self.player_id in self.player_states[self.room_name]:
                del self.player_states[self.room_name][self.player_id]
            
            if len(self.rooms[self.room_name]) == 0:
                # Clean up everything when room is empty
                del self.rooms[self.room_name]
                del self.game_boards[self.room_name]
                del self.solved_boards[self.room_name]
                del self.player_states[self.room_name]

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        # Notify other player about disconnect
        if self.room_name in self.rooms:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_update',
                    'count': len(self.rooms[self.room_name])
                }
            )

    async def initial_board_setup(self):
        """Initialize the game board with 2-6 numbers per 3x3 block"""
        # Initialize empty 9x9 board
        self.board = [[0 for _ in range(9)] for _ in range(9)]
        
        # Fill each 3x3 block with random numbers
        for block_row in range(0, 9, 3):
            for block_col in range(0, 9, 3):
                self.fill_block(block_row, block_col)
        
        # Create a copy of the initial board before solving
        initial_board = [row[:] for row in self.board]
        
        # Solve the board
        if self.solve_board():
            # Store the solved board
            self.solved_boards[self.room_name] = [row[:] for row in self.board]
            # Reset board to initial state for gameplay
            self.board = initial_board
            # Store the game board
            self.game_boards[self.room_name] = self.board
            
            # Update all players' boards with initial state
            for player_id in self.player_states[self.room_name]:
                self.player_states[self.room_name][player_id]['board'] = [row[:] for row in self.board]
            
            # Send the initial board to all players
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'board_update',
                    'board': self.board
                }
            )
        else:
            # If board is unsolvable, try again
            await self.initial_board_setup()

    def fill_block(self, start_row, start_col):
        """Fill a 3x3 block with 2-6 random numbers"""
        # Generate list of positions in the block
        positions = [(i + start_row, j + start_col) 
                    for i in range(3) 
                    for j in range(3)]
        
        # Randomly choose how many numbers to place (2-6)
        num_to_fill = random.randint(2, 6)
        
        # Randomly choose positions to fill
        positions_to_fill = random.sample(positions, num_to_fill)
        
        # Try to fill each chosen position
        for row, col in positions_to_fill:
            # Get list of valid numbers for this position
            valid_numbers = self.get_valid_numbers(row, col)
            if valid_numbers:
                # Choose a random valid number
                value = random.choice(valid_numbers)
                self.board[row][col] = value

    def get_valid_numbers(self, row, col):
        """Get list of valid numbers for a position"""
        valid = set(range(1, 10))
        
        # Remove numbers from same row
        for i in range(9):
            if self.board[row][i] != 0:
                valid.discard(self.board[row][i])
        
        # Remove numbers from same column
        for i in range(9):
            if self.board[i][col] != 0:
                valid.discard(self.board[i][col])
        
        # Remove numbers from same 3x3 block
        start_row, start_col = 3 * (row // 3), 3 * (col // 3)
        for i in range(3):
            for j in range(3):
                if self.board[start_row + i][start_col + j] != 0:
                    valid.discard(self.board[start_row + i][start_col + j])
        
        return list(valid)

    def is_safe(self, row, col, num):
        """Check if it's safe to place number at given position"""
        # Check row
        for x in range(9):
            if self.board[row][x] == num:
                return False
        
        # Check column
        for x in range(9):
            if self.board[x][col] == num:
                return False
        
        # Check 3x3 box
        start_row, start_col = 3 * (row // 3), 3 * (col // 3)
        for i in range(3):
            for j in range(3):
                if self.board[start_row + i][start_col + j] == num:
                    return False
        return True

    def solve_board(self):
        """Solve the Sudoku board using backtracking"""
        empty = self.find_empty()
        if not empty:
            return True
        
        row, col = empty
        for num in range(1, 10):
            if self.is_safe(row, col, num):
                self.board[row][col] = num
                if self.solve_board():
                    return True
                self.board[row][col] = 0
        return False

    def find_empty(self):
        """Find an empty cell in the board"""
        for i in range(9):
            for j in range(9):
                if self.board[i][j] == 0:
                    return (i, j)
        return None

    def create_puzzle(self):
        """Create puzzle by removing numbers while maintaining uniqueness"""
        # Create a copy of the solved board
        solution = [row[:] for row in self.board]
        
        # Calculate how many cells to remove (leave 38-40 cells)
        cells_to_remove = 81 - random.randint(38, 40)
        
        positions = [(i, j) for i in range(9) for j in range(9)]
        random.shuffle(positions)
        
        for pos in positions[:cells_to_remove]:
            row, col = pos
            temp = self.board[row][col]
            self.board[row][col] = 0
            
            # Make copy of board for solving
            board_copy = [row[:] for row in self.board]
            
            # If puzzle becomes unsolvable with this removal, restore the number
            if not self.has_unique_solution(board_copy):
                self.board[row][col] = temp

    def has_unique_solution(self, board):
        """Check if the puzzle has a unique solution"""
        solutions = []
        
        def find_empty(board):
            """Find an empty cell in the board"""
            for i in range(9):
                for j in range(9):
                    if board[i][j] == 0:
                        return (i, j)
            return None
        
        def is_safe(board, row, col, num):
            """Check if it's safe to place number at given position"""
            # Check row
            for x in range(9):
                if board[row][x] == num:
                    return False
            
            # Check column
            for x in range(9):
                if board[x][col] == num:
                    return False
            
            # Check 3x3 box
            start_row, start_col = 3 * (row // 3), 3 * (col // 3)
            for i in range(3):
                for j in range(3):
                    if board[start_row + i][start_col + j] == num:
                        return False
            return True
        
        def solve(board):
            if len(solutions) > 1:
                return
            
            empty = find_empty(board)
            if not empty:
                solutions.append([row[:] for row in board])
                return
            
            row, col = empty
            for num in range(1, 10):
                if is_safe(board, row, col, num):
                    board[row][col] = num
                    solve(board)
                    board[row][col] = 0
        
        solve(board)
        return len(solutions) == 1

    async def board_update(self, event):
        """Send board update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'board_update',
            'board': event['board'],
            'chances': self.player_states[self.room_name][self.player_id]['chances']
        }))
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        
        if 'move' in data:
            row = data['move']['row']
            col = data['move']['col']
            value = data['move']['value']
            
            # Get player's current state
            player_state = self.player_states[self.room_name][self.player_id]
            
            if player_state['is_eliminated']:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'You have been eliminated'
                }))
                return
            
            print("Solved Block :",self.solved_boards[self.room_name][row][col])
            # Check if move is correct
            if self.solved_boards[self.room_name][row][col] == value:
                # Update player's board
                player_state['board'][row][col] = value
                
                print(f"Debug - Updated player board at {row},{col} with {value}")
                print(f"Debug - Current player board state: {player_state['board']}")
                print("Solved Answer :",self.solved_boards[self.room_name])
                # Check if player has won
                if self.check_win(player_state['board']):
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'game_over',
                            'winner': self.player_id
                        }
                    )
                else:
                    # Send success message and updated board
                    await self.send(text_data=json.dumps({
                        'type': 'move_result',
                        'success': True,
                        'moveData': {
                            'row': row,
                            'col': col,
                            'value': value
                        },
                        'chances': player_state['chances']
                    }))
            else:
                # Wrong move - decrease chances
                player_state['chances'] -= 1
                
                await self.send(text_data=json.dumps({
                    'type': 'move_result',
                    'success': False,
                    'moveData': {
                        'row': row,
                        'col': col,
                        'value': value
                    },
                    'chances': player_state['chances'],
                    'message': 'Wrong move!'
                }))
                
                if player_state['chances'] == 0:
                    player_state['is_eliminated'] = True
                    # Check if other player wins by elimination
                    await self.check_game_over()

    def check_win(self, board):
        """Check if the board is completely and correctly filled"""
        return all(board[i][j] == self.solved_boards[self.room_name][i][j] 
                  for i in range(9) for j in range(9))

    async def check_game_over(self):
        """Check if game is over due to elimination"""
        room_players = self.player_states[self.room_name]
        eliminated_count = sum(1 for state in room_players.values() if state['is_eliminated'])
        
        if eliminated_count == len(room_players) - 1:
            # Find the non-eliminated player
            winner = next(player_id for player_id, state in room_players.items() 
                        if not state['is_eliminated'])
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_over',
                    'winner': winner
                }
            )

    async def game_over(self, event):
        """Handle game over event"""
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'is_winner': event['winner'] == self.player_id
        }))

    async def player_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_update',
            'count': event['count']
        }))

        
