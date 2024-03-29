import time
import subprocess
import socket

from config import ES_HOST_TUNNEL_CFG

es_local_tunnel_port = 9201


def port_open(host, port):
    s = socket.socket()
    try:
        s.connect((host, port))
        return True
    except socket.error:
        return False


class ESTunnelContextManager:
    def __init__(self):
        self.p = None

    def __enter__(self):
        assert not port_open('localhost', es_local_tunnel_port), 'localhost:{} is alreay open'.format(es_local_tunnel_port)
        tunnel_cmd = "ssh -o StrictHostKeyChecking=no -N -L {0}:localhost:9200 -C -i {key} {username}@{host}"
        tunnel_cmd = tunnel_cmd.format(es_local_tunnel_port, **ES_HOST_TUNNEL_CFG)
        self.p = subprocess.Popen(tunnel_cmd.split())
        time.sleep(2)
        if port_open('localhost', es_local_tunnel_port):
            print "ssh tunnel is running at localhost:{} (pid: {})...".format(es_local_tunnel_port, self.p.pid)
        else:
            print 'Error: localhost:{} failed to open'.format(es_local_tunnel_port)
        return self.p

    def __exit__(self, *exc_info):
        if self.p and self.p.poll() is None:
            self.p.kill()
            print "ssh tunnel is closed now."
            time.sleep(1)
            assert not port_open('localhost', es_local_tunnel_port), 'localhost:{} is still open'.format(es_local_tunnel_port)


def open_tunnel():
    return ESTunnelContextManager()
