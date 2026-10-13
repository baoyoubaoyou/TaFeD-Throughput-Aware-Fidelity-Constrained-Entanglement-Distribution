import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from npj_comparison_scheme_main import *
from qpath import *
from qpath_update import *
from qleap import *
from alg2k import *
from hopspf import *
import copy, time
import networkx as nx


# c作为自变量，单sd,数据保存于代码主文件夹下的txt文件中，运行次数count可以自定义。
# 算法输入为拓扑，源，目的，保真度阈值，请求数量。
# 算法返回值为：路径集，提纯决策集，保真度集，纠缠消耗集，吞吐量集，总吞吐量，寻路时间。

# 算法变量设置
# 总仿真次数
def SingleNC_Update(count=1, link_capacity=30,x=np.arange(50, 250, 20) ,topology_fidelity_mode=0, nrof_requests=10000, alg1_mode=1,
                     reqf=0.7, random_topology=0, random_topology_mode=0, random_topology_nodes_num=5):
    """
    count=10
    reqf=0.7
    #模式0代表重新生成，模式1代表读取之前保存的链路保真度数值
    topology_fidelity_mode=0
    #单S-Dpair的请求connection数量
    nrof_requests=500000
    #Alg1的运行模式，BFS搜索为0，k-shortest为1
    alg1_mode=1
    #链路容量设置
    link_capacity=50
    #c的范围,节点资源量
    x=np.arange(100,1000,100)
    #x=np.arange(0.7,0.75,0.005)
    #本次仿真中启用的对比算法

    # 随机拓扑设置，1代表开启
    random_topology = 1
    #0代表每次生成随机的，1代表读取文件中的拓扑
    random_topology_mode=0
    random_topology_nodes_num = 10
    """
    memmory = 50
    enable_Hspf = 0  # 基于跳数的
    enable_alg1 = 1
    enable_alg2 = 1
    enable_alg3 = 1
    enable_alg4 = 0
    start_time = time.time()
    graph_topology_file_name1 = 'random_topology_nodes_with_nrof_nodes_' + str(random_topology_nodes_num) + '.txt'
    graph_topology_file_name2 = 'random_topology_edges_with_nrof_nodes_' + str(random_topology_nodes_num) + '.txt'
    filename = 'Single_SDPair_vs_Capacity.txt'
    fp = open(filename, 'w')
    # 先写入数据标题
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
    fp.write(utput_label)

    stphspf = [0] * len(x)
    stpalg1 = [0] * len(x)
    stpalg2 = [0] * len(x)
    stpalg3 = [0] * len(x)
    stpalg4 = [0] * len(x)

    avefhopcount = [0] * len(x)
    avefalg1 = [0] * len(x)
    avefalg2 = [0] * len(x)
    avefalg3 = [0] * len(x)
    avefalg4 = [0] * len(x)  # 新建一个名为avefalg4的数组

    consuhopcount = [0] * len(x)
    consualg1 = [0] * len(x)
    consualg2 = [0] * len(x)
    consualg3 = [0] * len(x)
    consualg4 = [0] * len(x)  # 新建一个名为consualg4的数组

    timeh = [0] * len(x)
    time1 = [0] * len(x)
    time2 = [0] * len(x)
    time3 = [0] * len(x)
    time4 = [0] * len(x)  # 新建一个名为time4的数组

    countf = [0] * len(x)
    countf1 = [0] * len(x)
    countf2 = [0] * len(x)
    countf3 = [0] * len(x)
    countf4 = [0] * len(x)  # 新建一个名为countf4的数组

    purroundh = [0] * len(x)
    purround1 = [0] * len(x)
    purround2 = [0] * len(x)
    purround3 = [0] * len(x)
    purround4 = [0] * len(x)  # 新建一个名为purround4的数组
    sumResoure = 0

    QpathputiTime = 0
    QpathProcessTime = 0

    QpathFastPutiTime = 0
    QpathFastProcessTime = 0

    QpathMinCosttime = 0
    QpathMinCostPutiTime = 0

    QleapPutiTime = 0
    QleapProcessTime = 0

    for i in range(count):
        print('running ' + str(i) + ' time:', str(time.time() - start_time) + '\n')

        # fp.write(str(i)+'    '+str(sou)+'    '+str(des)+'    ')
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
            # nodes, edges, positions = create_random_topology(random_topology_nodes_num, 0.06, 1)
            network = Net().network
            network[0] = nodes
            network[1] = edges
            network, sumResoure = Vtopo().creatbasicvtopo(network, link_capacity, memmory,topology_fidelity_mode)
            g, edge_count = Vtopo().creatvtopo(network)

        else:
            # 采用骨干网拓扑
            network = Net().network
            # print("test")
            # print(len(network[0]))
            # print(len(network[1]))
            network = Vtopo().creatbasicvtopo(network, link_capacity, memmory,topology_fidelity_mode)
            g = Vtopo().creatvtopo(network)

        # x=np.arange(0.5,1,0.05)
        # 随机产生sd点
        sou = random.randint(0, len(g) - 1)
        des = random.randint(0, len(g) - 1)
        while des == sou:
            des = random.randint(0, len(g) - 1)
        print('source=', sou, 'des=', des)
        tphspf = []
        yalg1 = []
        yalg2 = []

        for j in range(len(x)):
            print("c: " + str(x[j]))
            g,sumResoure = Vtopo().changec(g, link_capacity,x[j])
            time_0 = time.time()

            if enable_Hspf == 1:
                path, d, fi, con, th, sumt, times, PutiTime = Hspf().hspf(copy.deepcopy(g), sou, des, reqf,
                                                                          nrof_requests)

                # print(path,d,fi,con,th,sumt)
                timeh[j] += times
                tmpsf = 0
                tmpsc = 0
                tmpr = 0
                for i in range(len(fi)):
                    tmpsf += fi[i]

                    for c in con[i]:
                        tmpsc += c
                    for r in d[i]:
                        tmpr += r
                if len(fi) > 0:
                    purroundh[j] += tmpr
                    avefhopcount[j] += (tmpsf / len(fi))
                    stphspf[j] += sumt
                    consuhopcount[j] += tmpsc
                    countf[j] += 1

            if enable_alg1 == 1:
                time_1 = time.time()
                path1, d1, fi1, con1, th1, sumt1, times1 = Qpath().alg1(copy.deepcopy(g), sou, des, reqf, nrof_requests,
                                                                        alg1_mode, 1, 0)

                QpathProcessTime += time.time() - time_1
                QpathputiTime += times1[1]
                # print(path1,d1,fi1,con1,th1,sumt1)
                time1[j] += times1[1]
                tmpsf1 = 0
                tmpsc1 = 0
                tmpr1 = 0
                for i in range(len(fi1)):
                    tmpsf1 += fi1[i]
                    for c in con1[i]:
                        tmpsc1 += c
                    for r in d1[i]:
                        tmpr1 += r
                if len(fi1) > 0:
                    purround1[j] += tmpr1
                    avefalg1[j] += (tmpsf1 / len(fi1))
                    stpalg1[j] += sumt1
                    consualg1[j] += tmpsc1
                    countf1[j] += 1

            if enable_alg2 == 1:
                path2, d2, fi2, con2, th2, sumt2, times2 = Qleap().alg2(copy.deepcopy(g), sou, des, reqf, nrof_requests)
                # print(path2,d2,fi2,con2,th2,sumt2)
                time2[j] += times2
                tmpsf2 = 0
                tmpsc2 = 0
                tmpr2 = 0
                for i in range(len(fi2)):
                    tmpsf2 += fi2[i]
                    for c in con2[i]:
                        tmpsc2 += c
                    for r in d2[i]:
                        tmpr2 += r
                if len(fi2) > 0:
                    purround2[j] += tmpr2
                    avefalg2[j] += (tmpsf2 / len(fi2))
                    stpalg2[j] += sumt2
                    consualg2[j] += tmpsc2
                    countf2[j] += 1

            if enable_alg3 == 1:
                time_3 = time.time()
                path3, d3, fi3, con3, th3, sumt3, times3 = Qpath_update().alg1_update(copy.deepcopy(g), sou, des, reqf,
                                                                                      nrof_requests,
                                                                                      alg1_mode, 4, 1, 0.2)
                QpathFastPutiTime += times3[1]
                QpathFastProcessTime += time.time() - time_3

                # print(path3, d3, fi3, con3, th3, sumt3)
                time3[j] += times3[1]
                tmpsf3 = 0
                tmpsc3 = 0
                tmpr3 = 0
                for i in range(len(fi3)):
                    tmpsf3 += fi3[i]
                    for c in con3[i]:
                        tmpsc3 += c
                    for r in d3[i]:
                        tmpr3 += r
                if len(fi3) > 0:
                    purround3[j] += tmpr3
                    avefalg3[j] += (tmpsf3 / len(fi3))
                    stpalg3[j] += sumt3
                    consualg3[j] += tmpsc3
                    countf3[j] += 1

            if enable_alg4 == 1:
                time_4 = time.time()
                path4, d4, fi4, con4, th4, sumt4, times4 = Qpath().alg1(copy.deepcopy(g), sou, des, reqf, nrof_requests,
                                                                        alg1_mode, 2, 1)
                QpathMinCostPutiTime += times4[1]
                QpathMinCosttime += time.time() - time_4

                # print(path4, d4, fi4, con4, th4, sumt4)
                time4[j] += times4[1]
                tmpsf4 = 0
                tmpsc4 = 0
                tmpr4 = 0
                for i in range(len(fi4)):
                    tmpsf4 += fi4[i]
                    for c in con4[i]:
                        tmpsc4 += c
                    for r in d4[i]:
                        tmpr4 += r
                if len(fi4) > 0:
                    purround4[j] += tmpr4
                    avefalg4[j] += (tmpsf4 / len(fi4))
                    stpalg4[j] += sumt4
                    consualg4[j] += tmpsc4
                    countf4[j] += 1

    print("Qpath_Most提纯时间: {}".format(QpathputiTime / (len(x) * count)))
    print("Qpath_Most处理时间: {}".format(QpathProcessTime / (len(x) * count)))
    print("Qpath_Fsat提纯时间: {}".format(QpathFastPutiTime / (len(x) * count)))
    print("Qpath_Fast处理时间: {}".format(QpathFastProcessTime / (len(x) * count)))
    print("Qpath_MinCost提纯时间: {}".format(QpathMinCostPutiTime / (len(x) * count)))
    print("Qpath_MinCost处理时间: {}".format(QpathMinCosttime / (len(x) * count)))

    for i in range(len(x)):

        stphspf[i] /= count
        stpalg1[i] /= count
        stpalg2[i] /= count
        stpalg3[i] /= count
        stpalg4[i] /= count

        if countf[i] == 0:
            countf[i] = 1
        avefhopcount[i] /= countf[i]

        if countf1[i] == 0:
            countf1[i] = 1
        avefalg1[i] /= countf1[i]

        if countf2[i] == 0:
            countf2[i] = 1
        avefalg2[i] /= countf2[i]

        if countf3[i] == 0:
            countf3[i] = 1
        avefalg3[i] /= countf3[i]

        if countf4[i] == 0:
            countf4[i] = 1
        avefalg4[i] /= countf4[i]

        consuhopcount[i] /= count * sumResoure
        consualg1[i] /= count * sumResoure
        consualg2[i] /= count * sumResoure
        consualg3[i] /= count * sumResoure
        consualg4[i] /= count

        timeh[i] /= count
        time1[i] /= count
        time2[i] /= count
        time3[i] /= count
        time4[i] /= count

        purroundh[i] /= countf[i]
        purround1[i] /= countf1[i]
        purround2[i] /= countf2[i]
        purround3[i] /= countf3[i]
        purround4[i] /= countf4[i]

        output_result = "节点资源数量: " + str(round(x[i], 2)) + "\n"
        if enable_Hspf == 1:
            output_result += '  Hspf算法---吞吐量：' + str(stphspf[i]) + ' 路径平均保真度：' + str(
                avefhopcount[i]) + ' 提纯次数：' + str(purroundh[i]) + ' 消耗纠缠数：' + str(
                consuhopcount[i]) + ' 运行时间：' + str(timeh[i]) + '\n'
        if enable_alg1 == 1:
            output_result += '  QpathMost算法---吞吐量：' + str(stpalg1[i]) + ' 路径平均保真度：' + str(
                avefalg1[i]) + ' 提纯次数：' + str(purround1[i]) + ' 消耗纠缠数：' + str(
                consualg1[i]) + ' 运行时间：' + str(time1[i]) + '\n'
        if enable_alg2 == 1:
            output_result += '  Qleap算法---吞吐量：' + str(stpalg2[i]) + ' 路径平均保真度：' + str(
                avefalg2[i]) + ' 提纯次数：' + str(purround2[i]) + ' 消耗纠缠数：' + str(
                consualg2[i]) + ' 运行时间：' + str(time2[i]) + '\n'
        if enable_alg3 == 1:
            output_result += '  QpathFast算法---吞吐量：' + str(stpalg3[i]) + ' 路径平均保真度：' + str(
                avefalg3[i]) + ' 提纯次数：' + str(purround3[i]) + ' 消耗纠缠数：' + str(
                consualg3[i]) + ' 运行时间：' + str(time3[i]) + '\n'
        if enable_alg4 == 1:
            output_result += '  QpathMinCost算法---吞吐量：' + str(stpalg4[i]) + ' 路径平均保真度：' + str(
                avefalg4[i]) + ' 提纯次数：' + str(purround4[i]) + ' 消耗纠缠数：' + str(
                consualg4[i]) + ' 运行时间：' + str(time4[i]) + '\n'

        output_result += '\n'
        print("output_result:" + output_result)

        # fp.write(str(x[i])+'    '+str(stphspf[i])+'    '+str(stpalg1[i])+'    '+str(stpalg2[i])+'    '+str(stpalg2k[i])+'    '+str(stpalg2k3[i])+'    '+str(stpalg2k4[i])+'    '+str(stpalg2k5[i])+'    '+str(avefhopcount[i])+'    '+str(avefalg1[i])+'    '+str(avefalg2[i])+'    '+str(avefalg2k[i])+'    '+str(avefalg2k3[i])+'    '+str(avefalg2k4[i])+'    '+str(avefalg2k5[i])+'    '+str(consuhopcount[i])+'    '+str(consualg1[i])+'    '+str(consualg2[i])+'    '+str(consualg2k[i])+'    '+str(consualg2k3[i])+'    '+str(consualg2k4[i])+'    '+str(consualg2k5[i])+'    '+str(timeh[i])+'    '+str(time1[i])+'    '+str(time2[i])+'    '+str(time2k[i])+'    '+str(time2k3[i])+'    '+str(time2k4[i])+'    '+str(time2k5[i])+'\n')
        fp.write(output_result)
    fp.close()
    if enable_Hspf == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Hspf_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stphspf[i]))
    if enable_alg1 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Qpath_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stpalg1[i]))
    if enable_alg2 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Qleap_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stpalg2[i]))
    if enable_alg3 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\SFTRAP_Throughput.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], stpalg3[i]))

    if enable_Hspf == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Hspf_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefhopcount[i]))
    if enable_alg1 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Qpath_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefalg1[i]))
    if enable_alg2 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Qleap_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefalg2[i]))
    if enable_alg3 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\SFTRAP_Fidelity.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], avefalg3[i]))

    if enable_Hspf == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Hspf_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consuhopcount[i]))
    if enable_alg1 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Qpath_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consualg1[i]))
    if enable_alg2 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\Qleap_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consualg2[i]))
    if enable_alg3 == 1:
        with open("E:\王智\王智\王智的毕设\输出结果\单S-D内存变化结果\SFTRAP_ConsumeResoure.txt", "w") as file:
            for i in range(len(x)):
                file.write("{:.3f}\t{:.3f}\n".format(x[i], consualg3[i]))

    fig1 = plt.figure()  # 吞吐量
    if enable_Hspf == 1:
        plt.plot(x, stphspf, color='red', label='Hspf algorithm')
    if enable_alg1 == 1:
        plt.plot(x, stpalg1, color='#FABB6E', label='Qpath algorithm')
    if enable_alg2 == 1:
        plt.plot(x, stpalg2, color='#FC8002', label='Qleap algorithm')
    if enable_alg3 == 1:
        plt.plot(x, stpalg3, color='#4995C6', label='SFTRAP algorithm')
    if enable_alg4 == 1:
        plt.plot(x, stpalg4, color='orange', label='pramaters algorithm')

    plt.title("")
    plt.xlabel('Node Capacity')
    plt.ylabel('Throughput(qbits/slot)')
    plt.legend()  # 创建图例
    fig1.savefig(r'E:\王智\王智\王智的毕设\输出结果\单S-D资源自变量结果\S-D throughput.png')
    plt.show()

    fig2 = plt.figure()  # 平均保真度
    if enable_Hspf == 1:
        plt.plot(x, avefhopcount, color='red', label='hspf algorithm')
    if enable_alg1 == 1:
        plt.plot(x, avefalg1, color='#FABB6E', label='Qpath algorithm')
    if enable_alg2 == 1:
        plt.plot(x, avefalg2, color='#FC8002', label='Qleap algorithm')
    if enable_alg3 == 1:
        plt.plot(x, avefalg3, color='#4995C6', label=' SFTRAP algorithm')
    if enable_alg4 == 1:
        plt.plot(x, avefalg4, color='orange', label='pramaters algorithm')

    plt.title("")
    plt.xlabel('Node Capacity')
    plt.ylabel('Average End-to-End Fidelity')
    plt.legend()  # 创建图例
    fig2.savefig(r'E:\王智\王智\王智的毕设\输出结果\单S-D资源自变量结果\S-D fidelity.png')
    plt.show()

    fig3 = plt.figure()  # 资源消耗
    if enable_Hspf == 1:
        plt.plot(x, consuhopcount, color='red', label='hspf algorithm')
    if enable_alg1 == 1:
        plt.plot(x, consualg1, color='#FABB6E', label='Qpath algorithm')
    if enable_alg2 == 1:
        plt.plot(x, consualg2, color='#FC8002', label='Qleap algorithm')
    if enable_alg3 == 1:
        plt.plot(x, consualg3, color='#4995C6', label='SFTRAP algorithm')
    if enable_alg4 == 1:
        plt.plot(x, consualg4, color='orange', label='pramaters algorithm')

    plt.title("")
    plt.xlabel('Node Capacity')
    plt.ylabel('Network Resource Utilization')
    plt.legend()  # 创建图例
    fig3.savefig(r'E:\王智\王智\王智的毕设\输出结果\单S-D资源自变量结果\S-D resource.png')
    plt.show()
