from mqpath_update import *
from mqleap_update import *
from mhopspf_update import *
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import random
import copy
import time
import numpy as np
import networkx as nx


# 多sd的链路容量作为自变量，count作为运行次数

# 算法变量设置
# 总仿真次数
def MultiSdC(count=5, x=np.arange(10, 100, 10), sumreq=400, fth=0.7, sdnum=4, topology_fidelity_mode=0,
             read_random_SDpair=0, random_topology=0, random_topology_mode=0, random_topology_nodes_num=10, alpha=0,
             beta=1, pathselect=0):
    """
    count=10
    #本次仿真中启用的对比算法

    #多S-D pair 数量
    sdnum = 4
    #端到端保真度阈值
    fth = 0.7
    # 链路容量设置

    #总请求连接数量
    sumreq = 400
    #链路容量设置
    x=np.arange(10,91,10)
    #模式0代表重新生成，模式1代表读取之前保存的链路保真度数值
    topology_fidelity_mode=0
    #是否通过读取SDpair对，模式0代表重新生成，以保证仿真的一致性
    read_random_SDpair = 0
    #随机生成的SDpair记录文件
    Multiple_SDpair_save_name=str(sdnum)+'SDpairs_record'+'.txt'
    # 随机拓扑设置，0代表不适用随机拓扑，1代表开启随机拓扑
    random_topology = 1
    #0代表每次生成随机的，1代表读取文件中的拓扑
    random_topology_mode=0
    random_topology_nodes_num = 10
    """

    Multiple_SDpair_save_name = str(sdnum) + 'SDpairs_record' + '.txt'
    link_capacity = 50
    enable_Hspf = 0  # 基于跳数的
    enable_alg1 = 1
    enable_alg2 = 1
    enable_alg3 = 0
    enable_alg4 = 1
    enable_alg5 = 0
    start_time = time.time()
    graph_topology_file_name1 = 'random_topology_nodes_with_nrof_nodes_' + str(random_topology_nodes_num) + '.txt'
    graph_topology_file_name2 = 'random_topology_edges_with_nrof_nodes_' + str(random_topology_nodes_num) + '.txt'

    start_time = time.process_time_ns()
    time_1_total = 0
    time_2_total = 0
    filename = 'Multiple_SDPairs_vs_Link_Capacity.txt'
    fp = open(filename, 'w')
    fp.write(
        'fth    tphopcount    tpalg1    tpalg2    avefhopcount    avefalg1    avefalg2    consuhopcount    consualg1    consualg2    avepathlengthhopcount    avepathlengthalg1    avepathlengthalg2    aveperconhopcount    aveperconalg1    aveperconalg2    timehop    timealg1    timealg2\n')

    stphspf = [0] * len(x)
    stpalg1 = [0] * len(x)
    stpalg2 = [0] * len(x)
    stpalg3 = [0] * len(x)
    stpalg4 = [0] * len(x)
    stpalg5 = [0] * len(x)  # 新增一个名为stpalg5的数组

    avefhopcount = [0] * len(x)
    avefalg1 = [0] * len(x)
    avefalg2 = [0] * len(x)
    avefalg3 = [0] * len(x)
    avefalg4 = [0] * len(x)
    avefalg5 = [0] * len(x)  # 新增一个名为avefalg5的数组

    consuhopcount = [0] * len(x)
    consualg1 = [0] * len(x)
    consualg2 = [0] * len(x)
    consualg3 = [0] * len(x)
    consualg4 = [0] * len(x)
    consualg5 = [0] * len(x)  # 新增一个名为consualg5的数组

    avepathlengthhopcount = [0] * len(x)
    avepathlengthalg1 = [0] * len(x)
    avepathlengthalg2 = [0] * len(x)
    avepathlengthalg3 = [0] * len(x)
    avepathlengthalg4 = [0] * len(x)
    avepathlengthalg5 = [0] * len(x)  # 新增一个名为avepathlengthalg5的数组

    aveperconhopcount = [0] * len(x)
    aveperconalg1 = [0] * len(x)
    aveperconalg2 = [0] * len(x)
    aveperconalg3 = [0] * len(x)
    aveperconalg4 = [0] * len(x)
    aveperconalg5 = [0] * len(x)  # 新增一个名为aveperconalg5的数组

    timeh = [0] * len(x)
    time1 = [0] * len(x)
    time2 = [0] * len(x)
    time3 = [0] * len(x)
    time4 = [0] * len(x)
    time5 = [0] * len(x)  # 新增一个名为time5的数组

    HspfPutiTime = 0
    HspfProcessTime = 0

    QpathputiTime = 0
    QpathProcessTime = 0

    QpathFastPutiTime = 0
    QpathFastProcessTime = 0

    QpathMinCosttime = 0
    QpathMinCostPutiTime = 0

    QleapPutiTime = 0
    QleapProcessTime = 0

    UpdatePathTime = 0
    UpdatePathPutiTime = 0

    ####################生成随机拓扑，返回nodes[],edges[],positions[]##################
    ##a = alpha, b = beta
    def create_random_topology(nodes_num=50, a=0.06, b=1):  ##a = alpha, b = beta
        nodes = []
        edges = []
        positions = []
        edges_cost = []
        topology = [[0 for i in range(110)] for j in range(110)]
        distance = [[0 for i in range(nodes_num)] for j in range(nodes_num)]
        for n in range(0, nodes_num):
            x = random.randint(0, 100)
            y = random.randint(0, 100)
            while topology[x][y] == 1:
                x = random.randint(0, 100)
                y = random.randint(0, 100)
            topology[x][y] = 1
            nodes.append(f"N{n}")
            positions.append([x, y])
        i = 0
        max_length = -1
        while i < nodes_num:
            j = i + 1
            while j < nodes_num:
                distance[i][j] = (abs(positions[i][0] - positions[j][0]) ** 2 + abs(
                    positions[i][1] - positions[j][1])) ** 0.5
                max_length = max(max_length, distance[i][j])
                j += 1
            i += 1
        i = 0
        while i < nodes_num:
            j = i + 1
            while j < nodes_num:
                p = b * math.exp(-distance[i][j] / (max_length * a))  ##a = alpha, b = beta
                if random.random() < p:
                    edges_cost.append(round(distance[i][j], 1))
                    edges.append((nodes[i], nodes[j]))
                    edges.append((nodes[j], nodes[i]))
                j += 1
            i += 1
        g = nx.Graph()  # create graph
        g.add_nodes_from(nodes)  # add nodes
        g.add_edges_from(edges)  # add edges
        nodes_position = dict(zip(nodes, positions))  #
        node_labels = dict(zip(nodes, nodes))  # label of nodes
        edge_labels = dict(zip(edges, edges_cost))  # label of edges
        nx.draw_networkx_nodes(g, nodes_position, node_size=100, node_color="#6CB6FF")  # draw nodes
        nx.draw_networkx_edges(g, nodes_position, edges)  # draw edges
        nx.draw_networkx_labels(g, nodes_position, node_labels)  # draw label of nodes
        # nx.draw_networkx_edge_labels(g, nodes_position, edge_labels=edge_labels)  # draw label of edges
        # plt.show()
        return nodes, edges, positions

    if read_random_SDpair == 0:
        Multiple_SDpair_record = open(Multiple_SDpair_save_name, 'w')
        Multiple_SDpair_record.close()
    for i in range(count):
        print('running ' + str(i) + ' time:', str(time.process_time_ns() - start_time) + '\n')

        tmpsdset = []
        sdset = []
        fiset = [fth] * sdnum
        reqset = []
        if random_topology == 1:
            total_nodes = random_topology_nodes_num
        else:
            total_nodes = 39

        if read_random_SDpair == 0:
            # 随机生成SD对
            while len(tmpsdset) < (sdnum * 2):
                t = random.randint(0, total_nodes - 1)
                if t not in tmpsdset:
                    tmpsdset.append(t)

            Multiple_SDpair_record = open(Multiple_SDpair_save_name, 'a')  # 以a模式打开写入指针默认指向末尾
            Multiple_SDpair_record.write("record" + str(i) + '\n')
            for index in range(len(tmpsdset)):
                Multiple_SDpair_record.write(str(tmpsdset[index]) + '\n')
            Multiple_SDpair_record.close()
        if read_random_SDpair == 1:
            Multiple_SDpair_record = open(Multiple_SDpair_save_name, 'r')
            label = 0
            read_count = 0
            for line in Multiple_SDpair_record.readlines():
                if line.startswith("record" + str(200 + i)):
                    label = 1
                    continue
                if label == 1:
                    if read_count < sdnum * 2:
                        # print(tmpsdset)
                        tmpsdset.append(int(line))
                        read_count += 1

        for i in range(sdnum):
            sdset.append(tuple([tmpsdset[2 * i], tmpsdset[2 * i + 1]]))
            # c
            reqset.append(sumreq // sdnum)

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
                    line = line.strip('\n')
                    # line = line.strip('\'')
                    nodes.append(line)
                for line in graph_edges_file.readlines():
                    line = line.strip('\n')
                    line.replace("''", "")
                    edges0.append(line)
                # nodes=graph_nodes_file.readlines()
                # edges=graph_edges_file.readlines
                print(edges0[0])
                edges = []
                for index in range(len(edges0) - 1):
                    # edges.append((edges0[index]))
                    # edges.append((nodes[j], nodes[i]))
                    edges.append(eval(edges0[index]))
                print(edges)
                # print(type(edges[1]))
            # 采用随机拓扑
            # nodes, edges, positions = create_random_topology(random_topology_nodes_num, 0.06, 1)
            network = Net().network
            network[0] = nodes
            network[1] = edges
            network = Vtopo().creatbasicvtopo(network, link_capacity, topology_fidelity_mode)
            g,edge_count = Vtopo().creatvtopo(network)

        else:
            # 采用骨干网拓扑
            network = Net().network
            network = Vtopo().creatbasicvtopo(network, link_capacity, topology_fidelity_mode)
            g,edge_count = Vtopo().creatvtopo(network)

        sumResoure = edge_count * link_capacity

        for j in range(len(x)):

            print('\tc=', x[j])
            newg = Vtopo().changec(copy.deepcopy(g), x[j])
            time_0 = time.time()
            if enable_Hspf == 1:
                path, th, fi, d, con, sumt = Mhopspf_update().alg5(copy.deepcopy(newg), sdset, fiset, reqset, alpha,
                                                                   beta)
                # print('time of alg5 :', time.time() - time_0, '\n')
                timeh[j] += time.time() - time_0
                tmpsf = 0
                tmpsc = 0
                tmp_count = 0
                tmp_pathlen = 0
                tmp_percon = 0
                for a in range(len(con)):  # 计算总消耗纠缠数、计算总f
                    for b in range(len(con[a])):
                        for c in range(len(con[a][b])):
                            tmpsc += con[a][b][c]
                            tmp_percon += d[a][b][c] + 1
                        if fi[a][b] > 0:
                            tmp_count += 1
                            tmpsf += fi[a][b]
                            tmp_pathlen += len(path[a][b]) - 1
                # 计算平均f,平均路径长度及路径消耗
                if tmp_count > 0:
                    tmpsf = tmpsf / tmp_count
                    avepathlengthhopcount[j] = tmp_pathlen / tmp_count
                    aveperconhopcount[j] = tmp_percon / tmp_count
                if tmpsf > 0:
                    stphspf[j] += sumt
                    consuhopcount[j] += tmpsc
                    avefhopcount[j] += tmpsf

            time_1 = time.time()
            if enable_alg1 == 1:
                # 基于算法1的最优搜索算法，设计的多SD Pair路由算法
                path1, th1, fi1, d1, con1, sumt1, putiTimeMost = MQpath_update().alg4(copy.deepcopy(newg), sdset, fiset,
                                                                                      reqset, alpha, beta, pathselect)

                print('\tMQpath time :', time.time() - time_1)
                time1[j] += time.time() - time_1
                tmpsf1 = 0
                tmpsc1 = 0
                tmp_count = 0
                tmp_pathlen = 0
                tmp_percon = 0
                for a in range(len(con1)):  # 计算总消耗纠缠数、计算总f
                    for b in range(len(con1[a])):
                        for c in range(len(con1[a][b])):
                            tmpsc1 += con1[a][b][c]
                            tmp_percon += d1[a][b][c] + 1
                        if fi1[a][b] > 0:
                            tmp_count += 1
                            tmpsf1 += fi1[a][b]
                            tmp_pathlen += len(path1[a][b]) - 1
                # 计算平均f
                if tmp_count > 0:
                    tmpsf1 = tmpsf1 / tmp_count
                    avepathlengthalg1[j] += tmp_pathlen / tmp_count
                    aveperconalg1[j] += tmp_percon / tmp_count
                if tmpsf1 > 0:
                    stpalg1[j] += sumt1
                    consualg1[j] += tmpsc1
                    avefalg1[j] += tmpsf1
            time_2 = time.time()
            if enable_alg2 == 1:
                # 基于算法2的最优搜索算法，设计的多SD Pair路由算法
                path2, th2, fi2, d2, con2, sumt2, putiTimeQleap = MQleap_update().alg3(copy.deepcopy(newg), sdset,
                                                                                       fiset, reqset, alpha, beta,
                                                                                       pathselect)
                print('\tMqleap time:', time.time() - time_2)
                time2[j] += time.time() - time_2
                tmpsf2 = 0
                tmpsc2 = 0
                tmp_count = 0
                tmp_pathlen = 0
                tmp_percon = 0
                for a in range(len(con2)):  # 计算总消耗纠缠数、计算总fi
                    for b in range(len(con2[a])):
                        for c in range(len(con2[a][b])):
                            tmpsc2 += con2[a][b][c]
                            tmp_percon += d2[a][b][c] + 1
                        if fi2[a][b] > 0:
                            tmp_count += 1
                            tmpsf2 += fi2[a][b]
                            tmp_pathlen += len(path2[a][b]) - 1
                # 计算平均f
                if tmp_count > 0:
                    tmpsf2 = tmpsf2 / tmp_count
                    avepathlengthalg2[j] += tmp_pathlen / tmp_count
                    aveperconalg2[j] += tmp_percon / tmp_count
                if tmpsf2 > 0:
                    stpalg2[j] += sumt2
                    consualg2[j] += tmpsc2
                    avefalg2[j] += tmpsf2

            if enable_alg3 == 1:
                time_3 = time.time()
                path3, th3, fi3, d3, con3, sumt3,putiTimeFast = MQpath_update().alg4(copy.deepcopy(newg), sdset,
                                                                                       fiset, reqset, alpha, beta,
                                                                                       pathselect,3,1,1,0.2)
                QpathFastPutiTime+=putiTimeFast
                QpathFastProcessTime+=time.time()-time_3
                print('time of WeightMincost :', time.time() - time_3)
                time3[j] += time.time() - time_3
                tmpsf3 = 0
                tmpsc3 = 0
                tmp_count = 0
                tmp_pathlen = 0
                tmp_percon = 0
                for a in range(len(con3)):  # 计算总消耗纠缠数、计算总f
                    for b in range(len(con3[a])):
                        for c in range(len(con3[a][b])):
                            tmpsc3 += con3[a][b][c]
                            tmp_percon += d3[a][b][c] + 1
                        if fi3[a][b] > 0:
                            tmp_count += 1
                            tmpsf3 += fi3[a][b]
                            tmp_pathlen += len(path3[a][b]) - 1
                # 计算平均f
                if tmp_count > 0:
                    tmpsf3 = tmpsf3 / tmp_count
                    avepathlengthalg3[j] += tmp_pathlen / tmp_count
                    aveperconalg3[j] += tmp_percon / tmp_count
                if tmpsf3 > 0:
                    stpalg3[j] += sumt3
                    consualg3[j] += tmpsc3
                    avefalg3[j] += tmpsf3

            if enable_alg4 == 1:
                time_4 = time.time()
                path4, th4, fi4, d4, con4, sumt4, RunTime = MQpath_update().alg4(copy.deepcopy(newg), sdset,
                                                                                       fiset, reqset, alpha, beta,
                                                                                       pathselect, 5, 1,1,0.2,weightque=[0.2,0.2,0.6])

                #print("路径寻找时间:", RunTime[0], "纯化时间:", RunTime[1], "更新资源时间:", RunTime[2],"整体时间：",time.time() - time_4)
                print("\tSFTRAP time",time.time() - time_4)
                QpathMinCosttime += time.time() - time_4
                time4[j] += time.time() - time_4
                tmpsf4 = 0
                tmpsc4 = 0
                tmp_count = 0
                tmp_pathlen = 0
                tmp_percon = 0
                for a in range(len(con4)):  # 计算总消耗纠缠数、计算总f
                    for b in range(len(con4[a])):
                        for c in range(len(con4[a][b])):
                            tmpsc4 += con4[a][b][c]
                            tmp_percon += d4[a][b][c] + 1
                        if fi4[a][b] > 0:
                            tmp_count += 1
                            tmpsf4 += fi4[a][b]
                            tmp_pathlen += len(path4[a][b]) - 1
                # 计算平均f
                if tmp_count > 0:
                    tmpsf4 = tmpsf4 / tmp_count
                    avepathlengthalg4[j] += tmp_pathlen / tmp_count
                    aveperconalg4[j] += tmp_percon / tmp_count
                if tmpsf4 > 0:
                    stpalg4[j] += sumt4
                    consualg4[j] += tmpsc4
                    avefalg4[j] += tmpsf4

            if enable_alg5 == 1:
                time_5 = time.time()
                path5, th5, fi5, d5, con5, sumt5, putiTimeFast = MQpath_update().alg4(copy.deepcopy(g), sdset, fiset,
                                                                                      reqset, alpha, beta, pathselect,
                                                                                      2, 0,)
                UpdatePathTime+= putiTimeFast

                UpdatePathTime += time.time() - time_5
                print('time of MQpathPriority :', time.time() - time_5, '\n')
                time5[j] += time.time() - time_5
                tmpsf5 = 0
                tmpsc5 = 0
                tmp_count = 0
                tmp_pathlen = 0
                tmp_percon = 0
                for a in range(len(con5)):  # 计算总消耗纠缠数、计算总f
                    for b in range(len(con5[a])):
                        for c in range(len(con5[a][b])):
                            tmpsc5 += con5[a][b][c]
                            tmp_percon += d5[a][b][c] + 1
                        if fi5[a][b] > 0:
                            tmp_count += 1
                            tmpsf5 += fi5[a][b]
                            tmp_pathlen += len(path5[a][b]) - 1
                # 计算平均f
                if tmp_count > 0:
                    tmpsf5 = tmpsf5 / tmp_count
                    avepathlengthalg5[j] += tmp_pathlen / tmp_count
                    aveperconalg5[j] += tmp_percon / tmp_count
                if tmpsf5 > 0:
                    stpalg5[j] += sumt5
                    consualg5[j] += tmpsc5
                    avefalg5[j] += tmpsf5

    for i in range(len(x)):
        stphspf[i] /= count
        stpalg1[i] /= count
        stpalg2[i] /= count
        stpalg3[i] /= count
        stpalg4[i] /= count
        stpalg5[i] /= count

        avefhopcount[i] /= count
        avefalg1[i] /= count
        avefalg2[i] /= count
        avefalg3[i] /= count
        avefalg4[i] /= count
        avefalg5[i] /= count


        consuhopcount[i] /= count * sumResoure  # hspf算法找到的路径消耗的资源量
        consualg1[i] /= count * sumResoure  # qpath算法找到的路径消耗的资源量
        consualg2[i] /= count * sumResoure  # qleap算法找到的路径消耗的资源量
        consualg3[i] /= count * sumResoure
        consualg4[i] /= count * sumResoure
        consualg5[i] /= count * sumResoure

        avepathlengthhopcount[i] /= count
        avepathlengthalg1[i] /= count
        avepathlengthalg2[i] /= count
        avepathlengthalg3[i] /= count
        avepathlengthalg4[i] /= count
        avepathlengthalg5[i] /= count

        aveperconhopcount[i] /= count
        aveperconalg1[i] /= count
        aveperconalg2[i] /= count
        aveperconalg3[i] /= count
        aveperconalg4[i] /= count
        aveperconalg5[i] /= count


        fp.write(str(x[i]) + '    ' + str(stphspf[i]) + '    ' + str(stpalg1[i]) + '    ' + str(stpalg2[i]) + '    ' +
                 str(avefhopcount[i]) + '    ' + str(avefalg1[i]) + '    ' + str(avefalg2[i]) + '    ' +
                 str(consuhopcount[i]) + '    ' + str(consualg1[i]) + '    ' + str(consualg2[i]) + '    ' +
                 str(avepathlengthhopcount[i]) + '    ' + str(avepathlengthalg1[i]) + '    ' + str(
            avepathlengthalg2[i]) + '    ' +
                 str(aveperconhopcount[i]) + '    ' + str(aveperconalg1[i]) + '    ' + str(aveperconalg2[i]) + '    ' +
                 str(timeh[i]) + '    ' + str(time1[i]) + '    ' + str(time2[i]) + '\n')

    fp.close()
    if enable_Hspf == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Hspf_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stphspf[i]))
    if enable_alg1 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Qpath_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stpalg1[i]))
    if enable_alg2 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Qleap_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stpalg2[i]))
    if enable_alg4 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\SFTRAP_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stpalg4[i]))

    if enable_Hspf == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Hspf_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefhopcount[i]))
    if enable_alg1 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Qpath_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefalg1[i]))
    if enable_alg2 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Qleap_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefalg2[i]))
    if enable_alg4 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\SFTRAP_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefalg4[i]))

    if enable_Hspf == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Hspf_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consuhopcount[i]))
    if enable_alg1 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Qpath_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consualg1[i]))
    if enable_alg2 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\Qleap_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consualg2[i]))
    if enable_alg4 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\SFTRAP_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consualg4[i]))
    fig1 = plt.figure()  # 吞吐量
    if enable_Hspf == 1:
        plt.plot(x, stphspf, color='red', label='Hspf algorithm')
    if enable_alg1 == 1:
        plt.plot(x, stpalg1, color='#FABB6E', label='Qpath algorithm')
    if enable_alg2 == 1:
        plt.plot(x, stpalg2, color='#FC8002', label='Qleap algorithm')
    if enable_alg3 == 1:
        plt.plot(x, stpalg3, color='blue', label='weight(0.2) algorithm')
    if enable_alg4 == 1:
        plt.plot(x, stpalg4, color='#4995C6', label='SFTRAP algorithm')
    if enable_alg5 == 1:
        plt.plot(x, stpalg5, color='origen', label='11 algorithm')
    plt.title("")
    plt.xlabel('Fidelity Threshold')
    plt.ylabel('Throughput(qbits/slot)')
    plt.legend()  # 创建图例
    fig1.savefig(r'E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\S-D throughput.png')
    plt.show()

    fig2 = plt.figure()  # 平均保真度
    if enable_Hspf == 1:
        plt.plot(x, avefhopcount, color='red', label='hspf algorithm')
    if enable_alg1 == 1:
        plt.plot(x, avefalg1, color='#FABB6E', label='Qpath algorithm')
    if enable_alg2 == 1:
        plt.plot(x, avefalg2, color='#FC8002', label='Qleap algorithm')
    if enable_alg3 == 1:
        plt.plot(x, avefalg3, color='blue', label='weight(0.2) algorithm')
    if enable_alg4 == 1:
        plt.plot(x, avefalg4, color='#4995C6', label='SFTRAP algorithm')
    if enable_alg5 == 1:
        plt.plot(x, avefalg5, color='orgine', label=' 11 algorithm')
    plt.title("")
    plt.xlabel('Fidelity Threshold')
    plt.ylabel('Average End-to-End Fidelity')
    plt.legend()  # 创建图例
    fig2.savefig(r'E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\S-D fidelity.png')
    plt.show()

    fig3 = plt.figure()  # 资源消耗
    if enable_Hspf == 1:
        plt.plot(x, consuhopcount, color='red', label='hspf algorithm')
    if enable_alg1 == 1:
        plt.plot(x, consualg1, color='#FABB6E', label='Qpath algorithm')
    if enable_alg2 == 1:
        plt.plot(x, consualg2, color='#FC8002', label='Qleap algorithm')
    if enable_alg3 == 1:
        plt.plot(x, consualg3, color='blue', label='weight(0.2) algorithm')
    if enable_alg4 == 1:
        plt.plot(x, consualg4, color='#4995C6', label='SFTRAP algorithm')
    if enable_alg5 == 1:
        plt.plot(x, consualg5, color='oringin', label='11 algorithm')
    plt.title("")
    plt.xlabel('Fidelity Threshold')
    plt.ylabel('Network Resource Utilization')
    plt.legend()  # 创建图例
    fig3.savefig(r'E:\王智\王智\王智的毕设\输出结果\多S-D资源自变量结果\S-D resource.png')
    plt.show()
    return True