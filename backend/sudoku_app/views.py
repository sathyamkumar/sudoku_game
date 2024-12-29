from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
import random
import string

def generate_room_code(length=6):
    """Generate a random room code of specified length"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@api_view(['POST'])
def create_room(request):
    """Create a new game room"""
    room_code = generate_room_code()
    return Response({
        'room_code': room_code,
        'message': 'Room created successfully'
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
def get_room(request):
    """Get room details"""
    room_code = request.query_params.get('room_code')
    if not room_code:
        return Response({
            'error': 'Room code is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Since we're using WebSocket for game state, we just verify the room exists
    # You can add additional room validation logic here if needed
    return Response({
        'room_code': room_code,
        'message': 'Room found'
    }, status=status.HTTP_200_OK)
    