# fp.write(str(i)+'    '+str(sou)+'    '+str(des)+'    ')

from typing import TextIO

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from npj_comparison_scheme_main import create_random_topology
from qpath import *
from  qpath_update import *
from qleap import *
from alg2k import *
from hopspf import *
import copy, time
import networkx as nx

class createTopology:
    def createTopology01(self,topology_fidelity_mode=1,random_topology=0,random_topology_mode=1,random_topology_nodes_num=5,
                         link_capacity=30 ):
        enable_Hspf: int = 1  # 基于跳数的
        enable_alg1 = 1
        enable_alg2 = 1
        enable_alg3 = 1
        enable_alg4 = 0
        enable_alg5 = 1

        graph_topology_file_name1 = 'random_topology_nodes_with_nrof_nodes_' + str(random_topology_nodes_num) + '.txt'
        graph_topology_file_name2 = 'random_topology_edges_with_nrof_nodes_' + str(random_topology_nodes_num) + '.txt'
        filename = 'Single_SDPair_vs_Fidelity.txt'
        #print('result saved in: ' + filename)
        utput_label = 'fth      '
        if enable_Hspf == 1:
            utput_label += 'throughput_hopCount      avgFidelity_hopCount      avepurround_hopCount      consumption_hopcount      time_hopCount      '
        if enable_alg1 == 1:
            utput_label += 'throughput_alg1      avgFidelity_alg1      avepurround_alg1      consumption_alg1      time_alg1      '
        if enable_alg2 == 1:
            utput_label += 'throughput_alg2      avgFidelity_alg2      avepurround_alg2      consumption_alg2      time_alg2'
        utput_label += '\n'
        # output_label = 'fth    tphopcount    tpalg1    tpalg2    tpalg2k    tpalg2k3    tpalg2k4    tpalg2k5    ' \
        #                    'avefhopcount    avefalg1    avefalg2    avefalg2k    avefalg2k3    avefalg2k4    avefalg2k5    ' \
        #                    'consuhopcount    consualg1    consualg2    consualg2k    consualg2k3    consualg2k4    consualg2k5    ' \
        #                    'timehop    timealg1    timealg2    timealg2k    timealg2k3    timealg2k4    timealg2k5\n'
        fp: TextIO = open(filename, 'w')
        fp.write(utput_label)

        if random_topology == 1:
            # 采用随机生成拓扑，或者读取相同的拓扑
            if random_topology_mode == 0:
                # 生成随机拓扑
                nodes, edges, positions = create_random_topology(random_topology_nodes_num, 0.5, 1)

                graph_topology_save_name1 = graph_topology_file_name1
                graph_topology_file1 = open(graph_topology_save_name1, 'w')
                graph_topology_save_name2 = graph_topology_file_name2
                graph_topology_file2 = open(graph_topology_save_name2, 'w')
                for index in range(len(nodes)):
                    graph_topology_file1.write(str(nodes[index]) + '\n')
                for index in range(len(edges)):
                    graph_topology_file2.write(str(edges[index]) + '\n')

            if random_topology_mode == 1:
                nodes = []
                edges0 = []
                # 读取已有的随机产生拓扑，以确保仿真的一致性
                graph_topology_save_name1 = graph_topology_file_name1
                graph_topology_save_name2 = graph_topology_file_name2
                graph_nodes_file = open(graph_topology_save_name1, 'r')
                graph_edges_file = open(graph_topology_save_name2, 'r')

                # 分别读取节点和边
                for line in graph_nodes_file.readlines():
                    line = line.strip('\n')  # 去除‘\n’
                    # line = line.strip('\'')
                    nodes.append(line)
                for line in graph_edges_file.readlines():
                    line = line.strip('\n')
                    line.replace("''", "")
                    edges0.append(line)
                # nodes=graph_nodes_file.readlines()
                # edges=graph_edges_file.readlines
                edges = []
                length = len(edges0) - 1
                for index in range(length):
                    # edges.append((edges0[index]))
                    # edges.append((nodes[j], nodes[i]))
                    # print(index)
                    # print(edges0[index])
                    edges.append(eval(edges0[index]))
                # print(edges)
                # print(type(edges[1]))
            # 采用随机拓扑
            nodes, edges, positions = create_random_topology(random_topology_nodes_num, 0.06, 1)
            network = Net().network
            network[0] = nodes
            network[1] = edges
            network = Vtopo().creatbasicvtopo(network, link_capacity, topology_fidelity_mode)
            g, edge_count = Vtopo().creatvtopo(network)

        else:
            # 采用骨干网拓扑
            network = Net().network

            network = Vtopo().creatbasicvtopo(network, link_capacity, topology_fidelity_mode)
            g, edge_count = Vtopo().creatvtopo(network)

        sumResoure = edge_count * link_capacity
        # x=np.arange(0.5,1,0.05)
        # 随机产生sd点
        sou = random.randint(0, len(g) - 1)
        des = random.randint(0, len(g) - 1)
        # sou = 25
        # des = 10
        while des == sou:
            des = random.randint(0, len(g) - 1)
        # print('source=', sou, 'des=', des)
        return g, sou, des,sumResoure
