from qpath import *
from network import *
from patharrange import *
from pathfd import *
from queue import PriorityQueue
import sys
import copy, random


# 基于算法1的最优搜索算法，设计的多SD Pair路由算法
class MQpath:
    def __init__(self):

        self.path = []  # 储存各sd对找到的路径
        self.fi = []  # 储存各路径的期望保真度
        self.d = []  # 储存路径纠缠提纯次数
        self.th = []  # 各路径期望吞吐量
        self.con = []  # 储存纠缠消耗数
        self.sdth = []  # 各sd对的吞吐量
        self.sumt = 0  # 网络总吞吐量
        self.q = PriorityQueue()

    def alg4(self, network, sdset, fthset, reqset, alpha=0, beta=1, pathselect=0,
             max_reallocation_rounds=None, max_candidate_paths=None):
        self.network = network
        """vnetwork=Vtopo().creatbasicvtopo(network)  #预处理拓扑，转换为合适的格式
        newnetwork=Vtopo().creatvtopo(vnetwork)"""
        # 计算节点自由度
        freed = Vtopo().calg(network)
        dicsd = {}
        # 初始化路径集、提纯、吞吐量,建立字典，映射关系为sd对
        for i in range(len(sdset)):
            self.path.append([])
            self.fi.append([])
            self.d.append([])
            self.th.append([])
            self.con.append([])
            self.sdth.append(0)
            dicsd[tuple(sdset[i])] = i
        # 建立字典，映射关系为sd对

        for i in range(len(sdset)):
            c = copy.deepcopy(network)
            # pathset:路径集合
            pathset, dset, fiset, conset, thset, sumt, t = Qpath().alg1(
                c, sdset[i][0], sdset[i][1], fthset[i], reqset[i],
                max_iterations=max_reallocation_rounds,
                max_candidate_paths=max_candidate_paths)
            pathfreed = []  # 初始化路径自由度
            for path in pathset:
                pathfreed.append(Cpathfd().calpathfd(path, freed))
            # 计算综合Utility，一次循环就是计算第j条路径
            uti = []
            for j in range(len(pathfreed)):
                uti.append(Cpathfd().caluti(pathfreed[j], dset[j]))
            # 放入优先队列
            for p in range(len(pathset)):
                # 按照uti[p]对路径集中的路径排序
                self.q.put((uti[p],
                            [[sdset[i][0], sdset[i][1], fthset[i], reqset[i]], pathset[p], conset[p], thset[p], dset[p],
                             fiset[p]]))
        rounds = 0
        while not self.q.empty():
            rounds += 1
            if max_reallocation_rounds is not None and rounds > max_reallocation_rounds:
                break
            if pathselect == 0:
                cur = self.q.get()[1]
            else:
                # 先将队列中的所有路径暂存到tmpq列表中，
                # 然后随机选择一个数值作为要选择的路径在队列中的位置，
                # 将该位置之前的路径都取出来，放入tmpq列表中，
                # 并取出该位置上的路径进行资源分配。
                # 最后再将tmpq列表中的路径重新放回队列中，以便后续的路径选择
                tmpq = []
                randompath = random.randint(1, len(self.q.queue))
                for i in range(randompath - 1):
                    tmpq.append(self.q.get())
                cur = self.q.get()[1]
                for i in tmpq:
                    self.q.put(i)

            # 资源分配
            # 判断当前路径资源是否充足
            if Udtp().preudtppathc(network, cur[1], cur[2]):
                # 更新topo资源
                Udtp().udtppathc(network, cur[1], cur[2])
                self.path[dicsd[tuple([cur[0][0], cur[0][1]])]].append(cur[1])
                self.th[dicsd[tuple([cur[0][0], cur[0][1]])]].append(cur[3])
                self.d[dicsd[tuple([cur[0][0], cur[0][1]])]].append(cur[4])
                self.fi[dicsd[tuple([cur[0][0], cur[0][1]])]].append(cur[5])
                self.sdth[dicsd[tuple([cur[0][0], cur[0][1]])]] += cur[3]
                self.con[dicsd[tuple([cur[0][0], cur[0][1]])]].append(cur[2])
                self.sumt += cur[3]

            else:  # 查找新路
                gcopy2 = copy.deepcopy(network)
                pathset, dset, fiset, conset, thset, sumt, t = Qpath().alg1(
                    gcopy2, cur[0][0], cur[0][1], cur[0][2],
                    cur[0][3] - self.sdth[dicsd[tuple([cur[0][0], cur[0][1]])]],
                    max_iterations=max_reallocation_rounds,
                    max_candidate_paths=max_candidate_paths)
                pathfreed = []  # 初始化路径自由度
                for i in pathset:
                    pathfreed.append(Cpathfd().calpathfd(i, freed))
                # 计算综合Utility
                uti = []
                for i in range(len(pathfreed)):
                    uti.append(Cpathfd().caluti(pathfreed[i], conset[i], alpha, beta))
                # 放入优先队列
                for i in range(len(pathset)):
                    self.q.put((uti[i], [cur[0], pathset[i], conset[i], thset[i], dset[i], fiset[i]]))

        return self.path, self.th, self.fi, self.d, self.con, self.sumt
