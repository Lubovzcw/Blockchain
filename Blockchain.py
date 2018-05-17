import hashlib
import json
import requests

from time import time
from urllib.parse import urlparse

from flask import Flask, jsonify, request


class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()

        # 创建区块链中的第一个区块
        block = {
            'index': 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': 100,
            'previous_hash': 1,
        }
        self.chain.append(block)  # 将生成的第一个区块添加到链表中

    def register_node(self, address):
        """
        注册一个新的节点信息
         -param address: 新节点的 address
        """
        parsed_url = urlparse(address)  # 将地址转化成 url

        self.nodes.add(parsed_url.netloc)  # 将转换后的 url 添加到临近节点集合中

    def new_block(self):
        """
        新增一个新的块内容
         -return: 返回新的链表
        """
        last_block = self.last_block

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': self.proof_of_work(last_block['proof']),
            'previous_hash': self.hash(last_block),
        }

        self.current_transactions = []  # 重置当前交易记录
        self.chain.append(block)  # 将新增的块添加到链中

        return block

    def new_transaction(self, sender, recipient, amount):
        """
        添加一次交易记录
         -param sender: 交易发起方标识
         -param recipient: 交易接收方标识
         -param amount: 交易的数量
         -return: 返回下一个区块(交易被添加到的区块)的索引值
        """
        self.current_transactions.append({
            '发送者的标识': sender,
            '接收者的标识': recipient,
            '交易数量': amount,
        })

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        """"
        将一个数据块进行 hash 操作
        我们必须确保这个字典（区块）是经过排序的，否则我们将会得到不一致的散列
         -param block: 一个数据块
         -return: 进行 hash 操作后的值
        """
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        """
        获取当前链表中的最后一个块
         -return: 返回链表最后一块
        """
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        """
        类似于 PoW 算法，工作量的证明
         -param last_proof: 上一个数据 proof
         -return: 新计算出来的 proof
        """
        proof = 0

        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        验证一个 proof 是否符合要求
        PoW 算法要求 last_proof 和 proof 组合出来的数据经过 sha256()计算后数据前四位必须为 0
         -param last_proof: 前一个块的 proof
         -param proof: 当前块计算出来的 proof
         -return: 是否符合要求
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()

        return guess_hash[:4] == '0000'

    def valid_chain(self, chain):
        """
        检查一个链表是否有效
        遍历每个块并验证和散列和工作证明
         -param chain: 一个链表
         -return: 链表是否有效
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]

            if block['previous_hash'] != self.hash(last_block):
                return False
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        解决冲突问题
        用最长有效链表规则, 实现网络中的共识问题，找到当前邻接节点中一条最长的并且有效的链表进行替换
         -return: 当前链表是否被替换
        """
        neighbours = self.nodes
        new_chain = None

        max_length = len(self.chain)

        for node in neighbours:

            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        if new_chain:
            self.chain = new_chain
            return True

        return False


app = Flask(__name__)

blockchain = Blockchain()


@app.route('/mine', methods=['GET'])
def mine():

    block = blockchain.new_block()

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }

    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    index = blockchain.new_transaction(values['sender'], values['recipient'],
                                       values['amount'])

    response = {'message': f'交易将会被添加到 Block 中 {index}'}
    return jsonify(response), 201


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')

    if nodes is None:
        return "当前节点附近节点为空，请添加临近节点信息...", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': "新节点已经被加入到链表中...",
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': "我们的链被替换了，新链如下：",
            'new_chain': blockchain.chain,
        }
    else:
        response = {
            'message': "Our chain was authoritative",
            'chain': blockchain.chain,
        }
    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001)
