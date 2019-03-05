import argparse
from enum import Enum
from os.path import isfile
from select import select
from socket import socket, AF_INET, SOCK_DGRAM
from struct import pack, unpack
from sys import argv, exit

# Create parser for user input
parser = argparse.ArgumentParser(description="Retrieve the file and store it on the local machine")
parser.add_argument('filename', help='name of the file to be retrieved')
parser.add_argument('--server', required=False, default='localhost:50001', help='server address from which, the file will be retrieved')
parser.add_argument('--timeout', type=int, required=False, default=2, help='number of seconds before re-sending a request to the server')
parser.add_argument('--maxtries', type=int, required=False, default=5, help='number of tries of re-sending a request to the server before giving up')

# if len(argv) <= 1:
#     print('Error: file name was not specified')
#     exit(1)

# Parse given user input
args = parser.parse_args(['message'])
print(args)

# Parse the given server address [optional]
addr_list = str(args.server).split(':')
if len(addr_list) != 2 or len(addr_list[0]) == 0 or len(addr_list[1]) == 0:
    print('Error: enter a valid server address i.e., IP:port')
    exit(1)

# open a file to write the retrieved file by the server
try:
    f = open(str(args.filename), 'w')
except FileNotFoundError:
    print('Error: specified file was not found') 
    exit(1)

# Enum class used to specify each state the client can be in
class State(Enum):
    READY = 0
    WAITING = 1 
    EXITING = 2

# Enum class used to specify the type of a message
class MsgType(Enum):
    DATA = 0
    REQUEST = 1
    ACK = 2
    ERROR = 3   

# Global variables used througout the system
client_socket = socket(AF_INET, SOCK_DGRAM)
fname = args.filename
last_ack_block = 0
max_tries = args.maxtries
server_addr = (addr_list[0], int(addr_list[1]))
state = State.READY
timeout = args.timeout
tries = 0

# Method to encode a message before sending it [encoding based on the defined protocol]
def encode_msg(is_last_block, msgtype, ack_block, payload):
    is_last_block_id = 0x10 if is_last_block else 0
    metadata = is_last_block_id + msgtype.value
    
    struct_fmt = "{}s".format(len(payload))
    payload = payload.encode()
    
    msg = pack('B', metadata)       # numbers are packed into hexadecimal strings to send them and easily manage them
    msg += pack('I', ack_block)
    msg += pack(struct_fmt, payload)

    return msg

# Method to decode a received message [encoding based on the defined protocol]
def decode_msg(msg):
    metadata = unpack('B', msg[:1])[0]
    ack_block = unpack('I', msg[1:5])[0]
    payload = msg[5:].decode()

    msgtype_mask = 0x0F         # first byte of metadata is divided into [msgtype | ackblock]
    lastblock_mask = 0x10

    is_last_block = metadata & lastblock_mask == 1  
    msgtype = metadata & msgtype_mask

    return is_last_block, msgtype, ack_block, payload

# Method to request a get operation to the server
def get(sock, retry=True):
    global f, fname, state, last_ack_block, server_addr 

    client_msgtype = MsgType.REQUEST if state == State.READY else MsgType.ACK
    stop_writing = False
         
    if retry == True:
        msg = encode_msg(True, client_msgtype, last_ack_block, fname)
        sock.sendto(msg, server_addr)
    else:
        msg, server_addr = sock.recvfrom(100)
        is_last_block, msgtype, ack_block, payload = decode_msg(msg)

        if msgtype == 0:
            if ack_block == last_ack_block + 1:     # checks that the received block is the next in the sequence
                f.write(payload)
                last_ack_block += 1
                state = State.WAITING
                stop_writing = is_last_block
                
            msg = encode_msg(True, MsgType.ACK, last_ack_block, fname)
            sock.sendto(msg, server_addr)  
        elif msgtype == MsgType.ERROR:
            print(payload)
            exit(1)

    return stop_writing

# map socket to function to call when socket is....
read_sockfunc = {}      # ready for reading
write_sockfunc = {}     # ready for writing
error_sockfunc = {}     # broken

read_sockfunc[client_socket] = get

# Send first request before sleeping for 'timeout' seconds
get(client_socket)
tries += 1

running = True
while running:
    read_rdyset, write_rdyset, err_rdyset = select(list(read_sockfunc.keys()),
                                                   list(write_sockfunc.keys()), 
                                                   list(error_sockfunc.keys()),
                                                   timeout)
    if not read_rdyset and not write_rdyset and not err_rdyset:
        print("retry")
        keep_trying = True
        if tries == max_tries: 
            print("Error: maximum number of tries was reached, would you like to keep trying? [t | f]")
            running = input('prompt') == "t"
        elif running: 
            tries += 1
            get(client_socket)
    else:
        print("a msg was received")
        tries = 0
        for sock in read_rdyset:
            if read_sockfunc[sock](sock, False):
                running = False
                break
