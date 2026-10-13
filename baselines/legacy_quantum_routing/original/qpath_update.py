from queue import PriorityQueue
from network import *
from spfmincost_update import *
from pathf import *
from updatetopo import *
from throughput import *
from pud import *
import sys
import copy, time


# searchchoice为1代表k最短，0代表暴力，puchoice0代表暴力1代表提纯增幅最大项。
class Qpath_update:
    def __init__(self):
        self.path = []  # 储存找到的路径
        self.fi = []  # 储存该路径的期望保真度
        self.d = []  # 储存纠缠提纯次数
        self.con = []  # 储存纠缠消耗数
        self.th = []  # 各路径期望吞吐量
        self.sumt = 0  # 总吞吐量
        self.notfound = []  # 储存迭代的路径
        self.sumpath = []
        self.flag1 = 1
        self.flag2 = 1
        self.putifyTime = 0
        self.RunTime = [0,0,0]#[路径寻找时间，纯化时间，更新资源时间]

    def alg1_update(self, network, source, des, fth, request, searchchoice=1, puchoice=1, costChoose=0,weight=0,weightQue=[0.33,0.33,0.33]):
        # searchchoice为1代表k最短，0代表暴力，puchoice=0：暴力，=1：MostUP提纯，=2：FastUp提纯
        # costChoose=1原算法的资源更新，=0 MinCost资源更新


        self.source = source
        self.des = des
        self.fth = fth
        self.request = request
        g = network
        a = []
        b = []
        count = 0
        self.q = PriorityQueue()
        times = 0
        times1 = 0
        # 计算ftable
        Pud().calftable(g)
        # 删边
        Udtp().udtp(g, self.fth)
        # cost转为跳数
        hopg = Udtp().topocost(g)
        # 转为临接表
        tng = Udtp().topoljb(hopg)
        # 计算最小跳数
        minhop = len(Spfmc().heapdijkstra_update(copy.deepcopy(tng), source, des)) - 1

        # 提前将cost小于minhop的路径遍历
        #self.notfound = Spfmc().spfmc2(tng, source, des, minhop - 1)  # 长度为cost但无法到达目的节点的路径
        for cost in range(minhop, sys.maxsize):  # 按cost搜索路径
            # print(cost)
            hopg = Udtp().topocost(g)
            ng = Udtp().topoljb(hopg)
            path = Spfmc().heapdijkstra(copy.deepcopy(ng), source, des)
            pathLen = len(path)
            if pathLen == 0:
                break
            if cost <= len(g) - 1:
                time_0 = time.time()
                if searchchoice == 0:  # 暴力求解
                    # if(self.flag2==1):
                    #     print("选择最优搜索路径方案")
                    #     self.flag2 = 0
                    pathset, self.notfound = Spfmc().walk(copy.deepcopy(ng), self.notfound, source, des, cost)
                    pathset1, a, b = Spfmc().costsearch(tng, source, des, cost, a, b,path)
                else:  # k最短求解路径
                    # if (self.flag2 == 1):
                    #print("选择K最短路径方案")
                    #     self.flag2 = 0
                    pathset, a, b = Spfmc().costsearch(copy.deepcopy(ng), source, des, cost, a, b,path)
                    reused_edges =self.count_reused_edges(pathset)
                #self.RunTime[0] += time.time() - time_0
                    # pathset是长度为cost的路径集合
                # 路径提纯
                time1=time.time()
                self.process_pathset(pathset, puchoice, g, self.fth,reused_edges,weight,weightQue)
                #self.RunTime[1]+=time.time()-time1
            # 吞吐量更新
            if cost > len(g) and self.q.empty():  # cost是路径长度
                break
            time2 = time.time()
            if not self.q.empty():
                if costChoose == 0:
                    self.update_throughput(cost, g, fth)
                elif costChoose == 1:
                    self.update_throughput_optimal(cost, g, fth)
            #self.RunTime[2] += time.time() - time2
        # print(self.sumpath)
        return self.path, self.d, self.fi, self.con, self.th, self.sumt, self.RunTime




    # 对找到的路径处理，使其满足保真度
    def process_pathset(self, pathset, puchoice, g, fth,reused_edges,weight,weightQue=[0.33,0.33,0.33]):

        for path in pathset:
            if Udtp().ispathconnect(g, path):
                if puchoice == 0:  # puchoice=0代表暴力提纯。
                    scost, tmpde = Pathf()._bfpathmincost(g, path, fth)
                    # if (self.flag1 == 1):
                    #     print("最优提纯".format(scost))
                    #     self.flag1 = 0
                elif puchoice == 1:  # 1代表提纯最小项
                    start_time = time.time()  # 记录开始时间
                    scost, tmpde = Pathf()._mostup(g, path, fth)  # 执行函数
                    end_time = time.time()  # 记录结束时间
                    self.putifyTime += end_time - start_time  # 计算函数执行时间
                    # if self.flag1 == 1:
                    #     print("最小项提纯".format(scost))
                    #     self.flag1 = 0
                    # 此时已经获得满足保真度的路径了，并且计算出来了路径的花销和提纯表，接下里就是计算吞吐量
                    # print("近优提纯：花销{}--提纯表{}".format(scost, tmpde))
                elif puchoice == 2:
                    start_time = time.time()  # 记录开始时间
                    scost, tmpde = Pathf()._fastup(g, path, fth)  # 执行函数
                    end_time = time.time()  # 记录结束时间
                    self.putifyTime += end_time - start_time
                elif puchoice == 3:
                    start_time = time.time()  # 记录开始时间
                    scost, tmpde = Pathf()._resuedFastup(g, path, fth,reused_edges,weight)  # 执行函数
                    end_time = time.time()  # 记录结束时间
                    self.putifyTime += end_time - start_time

                elif puchoice == 4:
                    start_time = time.time()  # 记录开始时间
                    scost, tmpde = Pathf()._mulprematers(g, path, fth,reused_edges,weight)  # 执行函数
                    end_time = time.time()  # 记录结束时间
                    self.putifyTime += end_time - start_time

                elif puchoice == 5:
                    start_time = time.time()  # 记录开始时间
                    scost, tmpde = Pathf()._mulprematersD(g, path, fth,reused_edges,weightQue)  # 执行函数
                    end_time = time.time()  # 记录结束时间
                    self.putifyTime += end_time - start_time

                else:
                    scost, tmpde = Pathf()._mostup1(g, path, fth)
                    # if self.flag1 == 1:
                    #     print("根据提升大小进行提纯".format(scost))
                    #     self.flag1 = 0
                #WeightedPriority = scost+sum(tmpde)
                WeightedPriority = scost

                if tmpde != []:
                    self.sumpath.append(path)
                    self.q.put((WeightedPriority, [path, tmpde]))  # 按花销从小到大排序



    # 计算路径的吞吐量，获得S-D能获得的最大的吞吐量
    def update_throughput(self, cost, g, fth):
        while not self.q.empty():
            cur = self.q.get()  # q.get((scost,[[path],[tmpde]]))
            if cur[0] <= cost + 1:  # 这条路径的花销和路径的长度对比，允许提纯一次？
                # 判断路径上是否有足够资源
                # n=1
                # print(cur)
                if Udtp().preudtppath(g, cur[1][0], cur[1][1]):
                    self.path.append(cur[1][0])  # 路径
                    # print(self.path)
                    self.d.append(cur[1][1])  # 路径上的提纯表
                    # 计算期望吞吐量
                    # 计算在该路径上消耗单份提纯资源的期望吞吐量
                    t_li = Etp().caletp(g, cur[1][0], cur[1][1])
                    # cur[1][0]:路径，cur[1][1]:提纯表
                    # 计算路径理论保真度
                    self.fi.append(Pathf()._epathf(g, cur[1][0], cur[1][1]))  # (scost,[path,tmpde])
                    # 计算该路径上所有资源的期望吞吐量
                    n = Etp().calpathsumth(g, cur[1][0], cur[1][1])
                    patht_li = n * t_li
                    if self.sumt + patht_li >= self.request:  # 该路径资源足以满足请求
                        for i in range(1, n + 1):
                            if self.sumt + i * t_li >= self.request:  # 源节点
                                self.th.append(i * t_li)
                                self.sumt = self.sumt + i * t_li
                                self.con.append(Etp().calactcon(cur[1][1], i))
                                break
                        return self.path, self.d, self.fi, self.con, self.th, self.sumt, self.putifyTime
                    else:  # 该路径总资源不满足需求，删去该路径重新查找
                        self.th.append(patht_li)
                        self.sumt = self.sumt + patht_li
                        self.con.append(Etp().calactcon(cur[1][1], n))
                    Udtp().udtppath(g, cur[1][0], Etp().calactcon(cur[1][1], n), fth)
                    # cur[1][0]:路径，cur[1][1]:提纯表
            else:
                self.q.put(cur)
                break

    def update_throughput_optimal(self, cost, g, fth):
        while not self.q.empty():
            cur = self.q.get()  # q.get((scost,[[path],[tmpde]]))
            if cur[0] <= cost + 1:  # 这条路径的花销和路径的长度对比，允许提纯一次？
                # 判断路径上是否有足够资源
                # n=1
                # print(cur)
                tetp = []
                if Udtp().preudtppath(g, cur[1][0], cur[1][1]):
                    self.path.append(cur[1][0])  # 路径
                    # print(self.path)
                    self.d.append(cur[1][1])  # 路径上的提纯表
                    # 计算期望吞吐量
                    # 计算在该路径上消耗单份提纯资源的期望吞吐量
                    t_li, tetp = Etp().caletp_optimal(g, cur[1][0], cur[1][1])
                    # cur[1][0]:路径，cur[1][1]:提纯表
                    # 计算路径理论保真度
                    self.fi.append(Pathf()._epathf(g, cur[1][0], cur[1][1]))  # (scost,[path,tmpde])
                    # 计算该路径上所有资源的期望吞吐量
                    n = Etp().calpathsumth(g, cur[1][0], cur[1][1])
                    patht_li = n * t_li
                    if self.sumt + patht_li >= self.request:  # 该路径资源足以满足请求
                        for i in range(1, n + 1):
                            if self.sumt + i * t_li >= self.request:  # 源节点
                                self.th.append(i * t_li)
                                self.sumt = self.sumt + i * t_li
                                self.con.append(Etp().calactcon_optimal(cur[1][1], patht_li, tetp))
                                break
                        return self.path, self.d, self.fi, self.con, self.th, self.sumt, self.putifyTime
                    else:  # 该路径总资源不满足需求，删去该路径重新查找
                        self.th.append(patht_li)
                        self.sumt = self.sumt + patht_li
                        self.con.append(Etp().calactcon_optimal(cur[1][1], patht_li, tetp))
                    Udtp().udtppath(g, cur[1][0], Etp().calactcon_optimal(cur[1][1], patht_li, tetp), fth)
                    # cur[1][0]:路径，cur[1][1]:提纯表
            else:
                self.q.put(cur)
                break
    # 使用适当的参数调用该函数
    def count_reused_edges(self,pathset):
        edge_count = {}

        for path in pathset:
            for i in range(len(path) - 1):
                node1, node2 = sorted([path[i], path[i + 1]])
                edge = (node1, node2)
                if edge in edge_count:
                    edge_count[edge] += 1
                else:
                    edge_count[edge] = 1

        reused_edges = {edge: count for edge, count in edge_count.items() if count > 1}
        # if reused_edges:
        #     min_value = min(reused_edges.values())
        #     reused_edges = {edge: count - min_value for edge, count in reused_edges.items()}

        return reused_edges



