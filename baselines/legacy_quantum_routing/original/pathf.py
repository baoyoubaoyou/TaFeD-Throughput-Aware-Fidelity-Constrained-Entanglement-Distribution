from throughput import *
from queue import PriorityQueue
import copy,math,sys
import heapq

class Pathf:
	def __init__(self):
		self._link=[0]  #初始化路径

	

	def _pathf(self,g,path):#计算未提纯时路径保真度
		f=1
		for i in range(len(path)-1):
			f=f*g[path[i]][path[i+1]]._f

		return f

	def _epathf(self,g,path,d):
		f=1
		for i in range(len(path)-1):
			f=f*g[path[i]][path[i+1]].ftable[d[i]][0]
		return f

	def _pathcost(self,g,path): #计算cost表中的cost
		sum=0
		for i in range(len(path)-1):
			sum+=g[path[i]][path[i+1]]
		return sum

	def _pathmincost(self,g,path,fth):#计算该路径满足fth的cost，以及提纯决定
		de=[]#初始化提纯决定
		pathf=[]
		for i in range(len(path)-1):
			de.append(0)
			pathf.append(g[path[i]][path[i+1]]._f)
		while self.pathfs(pathf)<fth:#每次最小的f提纯
			#查找最小的路径
			minf=10000000
			index=0
			for i in range(len(pathf)):
				if pathf[i]<minf:
					minf=pathf[i]
					index=i
			#进行提纯,更新提纯决定以及保真度
			
			de[index]+=1
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return 1000000,[]
			pathf[index]=Etp().calfg(pathf[index])
		#计算cost
		sumcost=0
		for i in de:
			sumcost+=2**i
		return sumcost,de
	def _pathmincost1(self,g,path,fth):
		#计算该路径满足fth的cost，以及提纯决定
		de=[]#初始化提纯决定
		flag=0.743
		pathf=[]
		for i in range(len(path)-1):
			de.append(0)
			pathf.append(g[path[i]][path[i+1]]._f)
		while self.pathfs(pathf)<fth:#每次距离0.77081最近的提纯
			#查找最小的路径
			minf=10000000
			index=0
			for i in range(len(pathf)):
				if abs(pathf[i]-flag)<minf:
					minf=abs(pathf[i]-flag)
					index=i
			#进行提纯,更新提纯决定以及保真度
			
			de[index]+=1
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return -1,[]
			pathf[index]=Etp().calfg(pathf[index])
		#计算cost
		sumcost=0
		for i in de:
			sumcost+=2**i
		return sumcost,de
	def _bfpathmincost(self,g,path,fth):#暴力搜索计算该路径满足fth的最小cost，以及提纯决定
		#判断路径所有资源能不能满足
		if self.prejudge(g,path,fth) is False:
			return -1,[]
		de=[[]]#初始化提纯决定
		alterde=[]#初始化可选提纯决定选项，路径上每条边能提出的次数
		
		for i in range(len(path)-1):
			alterde.append(len(g[path[i]][path[i+1]].ftable))
		for i in alterde:#计算所有提纯选项
			for j in range(len(de)):
				tmp=de.pop(0)
				for t in range(i):
					z=copy.deepcopy(tmp)
					z.append(t)
					de.append(z)#每条边可以提纯n个资源，一共有m条边，提纯的结果是：n^m的提纯方法

					#
		mincost=sys.maxsize
		tmpf=0
		mincostde=[]
		for i in de:
			pathf=[]#存入保真度
			for j in range(len(i)):
				pathf.append(g[path[j]][path[j+1]].ftable[i[j]][0])

			if self.pathfs(pathf)>=fth and self.ccost(i)<=mincost :
				if self.ccost(i)<mincost:
					mincost=self.ccost(i)
					mincostde=i
					tmpf=self.pathfs(pathf)
				else:
					if self.pathfs(pathf)>tmpf and self.ccost(i)==mincost:
						mincost=self.ccost(i)
						mincostde=i
						tmpf=self.pathfs(pathf)

		return mincost,mincostde
	def _mostup(self,g,path,fth):#每次提纯带来最大提升的一跳
		#判断路径所有资源能不能满足
		if self.prejudge(g,path,fth) is False:
			return -1,[]
		de=[]#初始化提纯决定
		pathf=[]
		for i in range(len(path)-1):
			de.append(0)
			pathf.append(g[path[i]][path[i+1]]._f)

		while self.pathfs(pathf)<fth:#每次提纯带来最大提升的一跳，
			#查找最大的提升
			tmpf=0
			index=0
			for i in range(len(pathf)):
				tmppathf=copy.deepcopy(pathf)
				tmppathf[i]=Etp().calfgn(tmppathf[i],g[path[i]][path[i+1]]._f)
				if self.pathfs(tmppathf)>tmpf:
					tmpf=self.pathfs(tmppathf)
					index=i
					tmp=tmppathf
			de[index]+=1
			#进行提纯,更新提纯决定以及保真度
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return -1,[]
			pathf=tmp

		return self.ccost(de),de

	def _fastup(self, g, path, fth):  # 每次提纯带来最大提升的一跳
		# 判断路径所有资源能不能满足
		if self.prejudge(g, path, fth) is False:
			return -1, []
		de = []  # 初始化提纯决定
		pathf = []
		for i in range(len(path) - 1):
			de.append(0)
			pathf.append(g[path[i]][path[i + 1]]._f)
		priority_queue1 = []
		while self.pathfs(pathf) < fth:  # 每次提纯带来最大提升的一跳，
			# 查找最大的提升
			tmpf = 0
			index = 0
			for i in range(len(pathf)):
				tmppathf = copy.deepcopy(pathf)
				tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)
				tmp = self.pathfs(tmppathf)
				heapq.heappush(priority_queue1, (-tmp, i,tmppathf[i]))#
			flag = 1
			for i in range(len(pathf)):
				if self.pathfs(pathf) < fth:
					if priority_queue1:
						tmp, i, tmppathf = heapq.heappop(priority_queue1)
						pathf[i] = tmppathf
						de[i] += 1
					else:
						if flag==1:#控制一条边上最多进行两次提纯
							tmppathf = copy.deepcopy(pathf)
							tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)
							tmp = self.pathfs(tmppathf)
							heapq.heappush(priority_queue1, (-tmp, i, tmppathf[i]))
							flag=0
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return -1,[]
		return self.ccost(de), de

	def _resuedFastup1(self, g, path, fth, reused_edges,weight):  # 每次提纯带来最大提升的一跳
		# 判断路径所有资源能不能满足
		if self.prejudge(g, path, fth) is False:
			return -1, []
		de = []  # 初始化提纯决定
		pathf = []
		for i in range(len(path) - 1):
			de.append(0)
			pathf.append(g[path[i]][path[i + 1]]._f)
		priority_queue2 = []
		while self.pathfs(pathf) < fth:  # 每次提纯带来最大提升的一跳，
			# 查找最大的提升
			tmpf = 0
			index = 0
			for i in range(len(pathf)):
				tmppathf = copy.deepcopy(pathf)
				ttmppathf = copy.deepcopy(pathf)
				tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)#某条边上的提纯后的保真度
				node1, node2 = sorted([path[i], path[i + 1]])
				edge = (node1, node2)
				reuWeight = reused_edges.get(edge, 0) * weight
				if reuWeight>0.1:
					reuWeight=0.1
				ttmppathf[i] = tmppathf[i]-reuWeight
				#tmp = self.pathfs(tmppathf)
				ttmp = self.pathfs(ttmppathf)#tmp只是一个排序的保真度
				heapq.heappush(priority_queue2, (-ttmp, i,tmppathf[i]))#
				#heapq.heappush(priority_queue3, (-tmp, i, tmppathf[i]))
			flag = 1
			for i in range(len(pathf)):
				if self.pathfs(pathf) < fth:
					if priority_queue2:
						tmp, i, tmppathf = heapq.heappop(priority_queue2)
						pathf[i] = tmppathf
						de[i] += 1
					else:
						if flag==1:#控制一条边上最多进行两次提纯
							tmppathf = copy.deepcopy(pathf)
							tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)
							tmp = self.pathfs(tmppathf)
							heapq.heappush(priority_queue2, (-tmp, i, tmppathf[i]))
							flag=0
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return -1,[]
		return self.ccost(de), de
	def _resuedFastup(self, g, path, fth, reused_edges,weight):  # 每次提纯带来最大提升的一跳
		# 判断路径所有资源能不能满足
		if self.prejudge(g, path, fth) is False:
			return -1, []
		de = []  # 初始化提纯决定
		pathf = []
		for i in range(len(path) - 1):
			de.append(0)
			pathf.append(g[path[i]][path[i + 1]]._f)
		priority_queues = {}
		while self.pathfs(pathf) < fth:  # 每次提纯带来最大提升的一跳，
			# 查找最大的提升
			tmpf = 0
			index = 0
			for i in range(len(pathf)):
				tmppathf = copy.deepcopy(pathf)
				ttmppathf = copy.deepcopy(pathf)
				tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)#某条边上的提纯后的保真度
				node1, node2 = sorted([path[i], path[i + 1]])
				edge = (node1, node2)
				reuWeight = reused_edges.get(edge, 0) * weight
				ttmppathf[i] = tmppathf[i]-reuWeight
				#tmp = self.pathfs(tmppathf)
				ttmp = self.pathfs(ttmppathf)#tmp只是一个排序的保真度
				if weight not in priority_queues:
					priority_queues[weight] = []
				heapq.heappush(priority_queues[weight], (-ttmp, i,tmppathf[i]))#
				#heapq.heappush(priority_queue3, (-tmp, i, tmppathf[i]))
			flag = 1
			for i in range(len(pathf)):
				if self.pathfs(pathf) < fth:
					if priority_queues.get(weight):
						tmp, index, tmppathf = heapq.heappop(priority_queues[weight])
						pathf[index] = tmppathf
						de[index] += 1
					else:
						if flag==1:#控制一条边上最多进行两次提纯
							tmppathf = copy.deepcopy(pathf)
							ttmppathf = copy.deepcopy(pathf)
							tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)
							reuWeight = reused_edges.get(edge, 0)  * weight
							ttmppathf[i] = tmppathf[i] - reuWeight
							ttmp = self.pathfs(ttmppathf)
							heapq.heappush(priority_queues[weight], (-ttmp, i, tmppathf[i]))
							flag=0
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return -1,[]
		return self.ccost(de), de


	def _mulprematers(self, g, path, fth, reused_edges,weight,resWeight=0.2):  # 每次提纯带来最大提升的一跳
		# 判断路径所有资源能不能满足
		if self.prejudge(g, path, fth) is False:
			return -1, []
		de = []  # 初始化提纯决定
		pathf = []
		for i in range(len(path) - 1):
			de.append(0)
			pathf.append(g[path[i]][path[i + 1]]._f)
		priority_queues = {}
		while self.pathfs(pathf) < fth:  # 每次提纯带来最大提升的一跳，
			# 查找最大的提升
			tmpf = 0
			index = 0
			for i in range(len(pathf)):
				tmppathf = copy.deepcopy(pathf)
				ttmppathf = copy.deepcopy(pathf)
				tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)#某条边上的提纯后的保真度
				node1, node2 = sorted([path[i], path[i + 1]])
				edge = (node1, node2)
				reuWeight = reused_edges.get(edge, 0) * weight
				resource=g[path[i]][path[i+1]]._c*resWeight
				ttmppathf[i] = tmppathf[i]-reuWeight+resource
				#tmp = self.pathfs(tmppathf)
				ttmp = self.pathfs(ttmppathf)#tmp只是一个排序的保真度
				if weight not in priority_queues:
					priority_queues[weight] = []
				heapq.heappush(priority_queues[weight], (-ttmp, i,tmppathf[i]))#
				#heapq.heappush(priority_queue3, (-tmp, i, tmppathf[i]))
			flag = 1
			for i in range(len(pathf)):
				if self.pathfs(pathf) < fth:
					if priority_queues.get(weight):
						tmp, index, tmppathf = heapq.heappop(priority_queues[weight])
						pathf[index] = tmppathf
						de[index] += 1
					else:
						if flag==1:#控制一条边上最多进行两次提纯
							tmppathf = copy.deepcopy(pathf)
							ttmppathf = copy.deepcopy(pathf)
							tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)
							reuWeight = reused_edges.get(edge, 0)  * weight
							ttmppathf[i] = tmppathf[i] - reuWeight
							ttmp = self.pathfs(ttmppathf)
							heapq.heappush(priority_queues[weight], (-ttmp, i, tmppathf[i]))
							flag=0
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return -1,[]
		return self.ccost(de), de

	def _mulprematersD(self, g, path, fth, reused_edges,resWeight=[0.33,0.34,0.44]):         # 每次提纯带来最大提升的一跳
		# 判断路径所有资源能不能满足
		if self.prejudge(g, path, fth) is False:
			return -1, []
		de = []  # 初始化提纯决定
		pathf = []
		for i in range(len(path) - 1):
			de.append(0)
			pathf.append(g[path[i]][path[i + 1]]._f)
		priority_queues = []
		maxFidelityDif, maxReused, maxC = self._normalization(g, path, reused_edges,pathf)#归一化
		while self.pathfs(pathf) < fth:  # 每次提纯带来最大提升的一跳，
			# 查找最大的提升
			index = 0
			for i in range(len(pathf)):
				tmppathf = copy.deepcopy(pathf)
				ttmppathf = copy.deepcopy(pathf)
				fidelityInitial =tmppathf[i]
				tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)#某条边上的提纯后的保真度
				difPathf = (tmppathf[i]-fidelityInitial)/maxFidelityDif
				node1, node2 = sorted([path[i], path[i + 1]])
				edge = (node1, node2)
				reuWeight = reused_edges.get(edge, 0) /maxReused
				resource=g[path[i]][path[i+1]]._c / maxC

				ttmppathf[i] = resWeight[0]*difPathf-resWeight[1]*reuWeight+resWeight[2]*resource
				#tmp = self.pathfs(tmppathf)


				heapq.heappush(priority_queues, (-ttmppathf[i], i,tmppathf[i]))#
				#heapq.heappush(priority_queue3, (-tmp, i, tmppathf[i]))
			flag = 1
			for i in range(len(pathf)):
				if self.pathfs(pathf) < fth:
					if len(priority_queues):
						tmp, index, tmppathf = heapq.heappop(priority_queues)
						pathf[index] = tmppathf
						de[index] += 1
					else:
						if flag==1:#控制一条边上最多进行两次提纯
							tmppathf = copy.deepcopy(pathf)
							ttmppathf = copy.deepcopy(pathf)
							fidelityInitial = tmppathf[i]
							tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)  # 某条边上的提纯后的保真度
							difPathf = (tmppathf[i] - fidelityInitial) / maxFidelityDif
							node1, node2 = sorted([path[i], path[i + 1]])
							edge = (node1, node2)
							reuWeight = reused_edges.get(edge, 0) / maxReused
							resource = g[path[i]][path[i + 1]]._c / maxC
							ttmppathf[i] = resWeight[0] * difPathf - resWeight[1] * reuWeight + resWeight[2] * resource
							# tmp = self.pathfs(tmppathf)
							heapq.heappush(priority_queues, (-ttmppathf[i], i, tmppathf[i]))  #
							flag=0
			if de[index]>=len(g[path[index]][path[index+1]].ftable):
				return -1,[]
		return self.ccost(de), de

	def _normalization(self, g, path, reused_edges,pathf):
		maxFidelityDif = 0
		maxReused = 0
		maxC = 0

		# 归一化处理
		for i in range(len(pathf)):
			tmppathf = copy.deepcopy(pathf)
			initial = tmppathf[i]
			tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)  # 某条边上的提纯后的保真度
			dif = tmppathf[i] - initial
			maxFidelityDif = maxFidelityDif if maxFidelityDif > dif else dif
			node1, node2 = sorted([path[i], path[i + 1]])
			edge = (node1, node2)
			maxReused = maxReused if maxReused > reused_edges.get(edge, 0) else reused_edges.get(edge, 0)
			maxC = maxC if maxC > g[path[i]][path[i + 1]]._c else g[path[i]][path[i + 1]]._c
		if maxFidelityDif == 0:
			maxFidelityDif = 1
		if maxReused == 0:
			maxReused = 1
		if maxC == 0:
			maxC = 1
		return maxFidelityDif,maxReused,maxC

	def _resuedFastupfail(self, g, path, fth, reused_edges, weight):
		if self.prejudge(g, path, fth) is False:
			return -1, []

		de = [0] * (len(path) - 1)  # 初始化提纯决定
		pathf = [g[path[i]][path[i + 1]]._f for i in range(len(path) - 1)]

		priority_queues = {}  # 为每个weight创建一个优先级队列
		while self.pathfs(pathf) < fth:
			for i in range(len(pathf)):
				tmppathf = copy.deepcopy(pathf)
				tmppathf[i] = Etp().calfgn(tmppathf[i], g[path[i]][path[i + 1]]._f)
				node1, node2 = sorted([path[i], path[i + 1]])
				edge = (node1, node2)
				reuWeight = reused_edges.get(edge, 0) ** 2 * weight
				# if reuWeight > 0.1:
				# 	reuWeight = 0.1
				tmppathf[i] -= reuWeight
				ttmp = self.pathfs(tmppathf)
				if weight not in priority_queues:
					priority_queues[weight] = []
				heapq.heappush(priority_queues[weight], (-ttmp, i, tmppathf[i]))

			for i in range(len(pathf)):
				if self.pathfs(pathf) < fth:
					if priority_queues.get(weight):
						tmp, index, tmppathf = heapq.heappop(priority_queues[weight])
						pathf[index] = tmppathf
						de[index] += 1
					else:
						if de[index] >= len(g[path[index]][path[index + 1]].ftable):
							return -1, []
		return self.ccost(de), de


	def _mostup1(self,g,path,fth): #根据每次提升大小决定提纯决策
		de=[0]*(len(path)-1)#初始化提纯决定
		#维护一个优先队列
		self.q=PriorityQueue()
		pathf=[]
		for i in range(len(path)-1):
			pathf.append(g[path[i]][path[i+1]]._f)
		#建立提纯提升索引表
		purup=[]
		#计算每一跳的提纯提升索引表
		for i in range(len(path)-1):
			tmp=[]
			for j in range(len(g[path[i]][path[i+1]].ftable)):
				ttmp=[]
				ttmp.append(i)
				if j<len(g[path[i]][path[i+1]].ftable)-1:
					ttmp.append(g[path[i]][path[i+1]].ftable[j+1][0]-g[path[i]][path[i+1]].ftable[j][0])#保真度提升大小
				else:
					ttmp.append(0)
				ttmp.append(j)
				if j==0:
					ttmp.append(1)
				else:
					ttmp.append(2**(j-1))#提升带来的花销
					#ttmp存放的是[边:i,保真度提升:第j次提纯带来的保真度提升,j：第j次提纯,这一次提纯消耗的资源]
				tmp.append(ttmp)#存放的是从0-j次提纯对于的ttmp表
			purup.append(tmp)
		#初始化队列
		for i in purup:
			self.q.put([1-i[0][1],i[0]])#按照第一次提纯，保真度提升从大到小排序，
		while self.pathfs(pathf)<fth:
			cur=self.q.get()
			curlist=cur[1]#[边:i,保真度提升:第0次提纯带来的保真度提升,j：第0次提纯,这一次提纯消耗的资源]
			if curlist[3]<2:#当前的cost增加为1
				de[curlist[0]]+=1
				if de[curlist[0]]>=len(g[path[curlist[0]]][path[curlist[0]+1]].ftable):
					return 0,[]
				pathf[curlist[0]]=Etp().calfg(pathf[curlist[0]])#更新该边的保真度
				curlist=purup[curlist[0]][curlist[2]] #重新放入队列
				self.q.put([1-curlist[1],curlist])
			else:#cost增加不为1，那么有多种提纯可能,找出这种提纯可能
				sumcost=curlist[3]#花销
				tmpcost=0
				tmpde1=de
				tmpde2=de
				tmpde1[curlist[0]]+=1
				tmpcurl=[]
				tmpout=[]
				while sumcost>0 and not self.q.empty():
					cur=self.q.get()
					curl=cur[1]
					if curl[3]<=sumcost:
						sumcost-=curl[3]
						tmpcurl.append(curl)
						tmpde2[curl[0]]+=1
					else:
						tmpout.append(cur) #暂时弹出稍后回填
				for i in tmpout:
					self.q.put(i) #回填
					
				if self._calf(g,path,tmpde1)>self._calf(g,path,tmpde2):
					de=tmpde1
					for i in tmpcurl:
						self.q.put([1-i[1],i])
					pathf[curlist[0]]=Etp().calfg(pathf[curlist[0]])
					curlist=purup[curlist[0]][curlist[2]] #重新放入队列
					self.q.put([1-curlist[1],curlist])
				else:
					de=tmpde2
					self.q.put([1-curlist[1],curlist])
					for i in tmpcurl:
						pathf[i[0]]=Etp().calfg(pathf[i[0]])
						i=purup[i[0]][i[2]] #重新放入队列
						self.q.put([1-i[1],i])
				for i in range(len(de)):
					if de[i]>=len(g[path[i][i+1]].ftable):
						return 0,[]
		return self.ccost(de),de

	def _calf(self,g,path,de):#根据提纯决定计算路径保真度
		pathf=[]
		for j in range(len(path)-1):
				pathf.append(g[path[j]][path[j+1]].ftable[de[j]][0])
		return self.pathfs(pathf)

	def ccost(self,de):
		sum=0
		for i in de:
			sum+=i+1
		return sum
	def cround(self,de):
		sum=0
		for i in de:
			sum+=i
		return sum
	def pathfs(self,pathf):
		f=1
		for i in pathf:
			f*=i
		return f
	def logpathfs(self,pathf):
		sum = 0;
		for i in pathf:
			sum+=math.log(i)
		return sum

	def prejudge(self,g,path,fth): #提前判断
		pathf=[]
		#判断是否依然联通
		for i in range(len(path)-1):
			if g[path[i]][path[i+1]]._isconnected==False:
				return False
		#判断最大保真度能否满足要求
		for i in range(len(path)-1):
			if len(g[path[i]][path[i+1]].ftable) > 0:
				pathf.append(g[path[i]][path[i+1]].ftable[-1][0])
			else:
				return False
		if self.pathfs(pathf)<fth:
			return False
		return True

	def noring(self,path):#判断是否有环
		for i in range(len(path)):
			for j in range(i+1,len(path)):
				if path[i]==path[j]:
					return False
		return True

	def pathfljb(self,g,path):
		f=1
		for i in range(len(path)-1):
			#找出对应路径
			for j in g[path[i]]:
				if j[0]==path[i+1]:
					f*=j[1]

		return f




