import os
import re
import sys
import cv2
import math
import time
import scipy
import argparse
import matplotlib
import numpy as np
import pylab as plt
#from joblib import Parallel, delayed
import util
import torch
import torch as T
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from collections import OrderedDict
from config_reader import config_reader
from scipy.ndimage.filters import gaussian_filter
import scipy.io as sio
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('name', type = str, help = 'the name of avi or image')
parser.add_argument('aori', type = str, help = 'the type of input data: (avi or jpg)')
parser.add_argument('scale', type = float, help = 'scale: (0.1~1)')
args = parser.parse_args()


torch.set_num_threads(1)
weight_name = './model/pose_model.pth'

blocks = {}

# find connection in the specified sequence, center 29 is in the position 15
limbSeq = [[2,3], [2,6], [3,4], [4,5], [6,7], [7,8], [2,9], [9,10], \
           [10,11], [2,12], [12,13], [13,14], [2,1], [1,15], [15,17], \
           [1,16], [16,18], [3,17], [6,18]]

# the middle joints heatmap correpondence
mapIdx = [[31,32], [39,40], [33,34], [35,36], [41,42], [43,44], [19,20], [21,22], \
          [23,24], [25,26], [27,28], [29,30], [47,48], [49,50], [53,54], [51,52], \
          [55,56], [37,38], [45,46]]

# visualize
colors = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0], \
          [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], \
          [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]


block0  = [{'conv1_1':[3,64,3,1,1]},{'conv1_2':[64,64,3,1,1]},{'pool1_stage1':[2,2,0]},{'conv2_1':[64,128,3,1,1]},{'conv2_2':[128,128,3,1,1]},{'pool2_stage1':[2,2,0]},{'conv3_1':[128,256,3,1,1]},{'conv3_2':[256,256,3,1,1]},{'conv3_3':[256,256,3,1,1]},{'conv3_4':[256,256,3,1,1]},{'pool3_stage1':[2,2,0]},{'conv4_1':[256,512,3,1,1]},{'conv4_2':[512,512,3,1,1]},{'conv4_3_CPM':[512,256,3,1,1]},{'conv4_4_CPM':[256,128,3,1,1]}]

blocks['block1_1']  = [{'conv5_1_CPM_L1':[128,128,3,1,1]},{'conv5_2_CPM_L1':[128,128,3,1,1]},{'conv5_3_CPM_L1':[128,128,3,1,1]},{'conv5_4_CPM_L1':[128,512,1,1,0]},{'conv5_5_CPM_L1':[512,38,1,1,0]}]

blocks['block1_2']  = [{'conv5_1_CPM_L2':[128,128,3,1,1]},{'conv5_2_CPM_L2':[128,128,3,1,1]},{'conv5_3_CPM_L2':[128,128,3,1,1]},{'conv5_4_CPM_L2':[128,512,1,1,0]},{'conv5_5_CPM_L2':[512,19,1,1,0]}]

for i in range(2,7):
    blocks['block%d_1'%i]  = [{'Mconv1_stage%d_L1'%i:[185,128,7,1,3]},{'Mconv2_stage%d_L1'%i:[128,128,7,1,3]},{'Mconv3_stage%d_L1'%i:[128,128,7,1,3]},{'Mconv4_stage%d_L1'%i:[128,128,7,1,3]},
{'Mconv5_stage%d_L1'%i:[128,128,7,1,3]},{'Mconv6_stage%d_L1'%i:[128,128,1,1,0]},{'Mconv7_stage%d_L1'%i:[128,38,1,1,0]}]
    blocks['block%d_2'%i]  = [{'Mconv1_stage%d_L2'%i:[185,128,7,1,3]},{'Mconv2_stage%d_L2'%i:[128,128,7,1,3]},{'Mconv3_stage%d_L2'%i:[128,128,7,1,3]},{'Mconv4_stage%d_L2'%i:[128,128,7,1,3]},
{'Mconv5_stage%d_L2'%i:[128,128,7,1,3]},{'Mconv6_stage%d_L2'%i:[128,128,1,1,0]},{'Mconv7_stage%d_L2'%i:[128,19,1,1,0]}]

def make_layers(cfg_dict):
    layers = []
    for i in range(len(cfg_dict)-1):
        one_ = cfg_dict[i]
        for k,v in one_.iteritems():
            if 'pool' in k:
                layers += [nn.MaxPool2d(kernel_size=v[0], stride=v[1], padding=v[2] )]
            else:
                conv2d = nn.Conv2d(in_channels=v[0], out_channels=v[1], kernel_size=v[2], stride = v[3], padding=v[4])
                layers += [conv2d, nn.ReLU(inplace=True)]
    one_ = cfg_dict[-1].keys()
    k = one_[0]
    v = cfg_dict[-1][k]
    conv2d = nn.Conv2d(in_channels=v[0], out_channels=v[1], kernel_size=v[2], stride = v[3], padding=v[4])
    layers += [conv2d]
    return nn.Sequential(*layers)

layers = []
for i in range(len(block0)):
    one_ = block0[i]
    for k,v in one_.iteritems():
        if 'pool' in k:
            layers += [nn.MaxPool2d(kernel_size=v[0], stride=v[1], padding=v[2] )]
        else:
            conv2d = nn.Conv2d(in_channels=v[0], out_channels=v[1], kernel_size=v[2], stride = v[3], padding=v[4])
            layers += [conv2d, nn.ReLU(inplace=True)]

models = {}
models['block0']=nn.Sequential(*layers)

for k,v in blocks.iteritems():
    models[k] = make_layers(v)

class pose_model(nn.Module):
    def __init__(self,model_dict,transform_input=False):
        super(pose_model, self).__init__()
        self.model0   = model_dict['block0']
        self.model1_1 = model_dict['block1_1']
        self.model2_1 = model_dict['block2_1']
        self.model3_1 = model_dict['block3_1']
        self.model4_1 = model_dict['block4_1']
        self.model5_1 = model_dict['block5_1']
        self.model6_1 = model_dict['block6_1']

        self.model1_2 = model_dict['block1_2']
        self.model2_2 = model_dict['block2_2']
        self.model3_2 = model_dict['block3_2']
        self.model4_2 = model_dict['block4_2']
        self.model5_2 = model_dict['block5_2']
        self.model6_2 = model_dict['block6_2']

    def forward(self, x):
        out1 = self.model0(x)

        out1_1 = self.model1_1(out1)
        out1_2 = self.model1_2(out1)
        out2  = torch.cat([out1_1,out1_2,out1],1)

        out2_1 = self.model2_1(out2)
        out2_2 = self.model2_2(out2)
        out3   = torch.cat([out2_1,out2_2,out1],1)

        out3_1 = self.model3_1(out3)
        out3_2 = self.model3_2(out3)
        out4   = torch.cat([out3_1,out3_2,out1],1)

        out4_1 = self.model4_1(out4)
        out4_2 = self.model4_2(out4)
        out5   = torch.cat([out4_1,out4_2,out1],1)

        out5_1 = self.model5_1(out5)
        out5_2 = self.model5_2(out5)
        out6   = torch.cat([out5_1,out5_2,out1],1)

        out6_1 = self.model6_1(out6)
        out6_2 = self.model6_2(out6)

        return out6_1,out6_2


model = pose_model(models)
model.load_state_dict(torch.load(weight_name))
model.cuda()
model.float()
model.eval()

param_, model_ = config_reader()

#torch.nn.functional.pad(img pad, mode='constant', value=model_['padValue'])
tic = time.time()
#test_image = './sample_image/ski.jpg'

if os.path.exists('sample_image/'+args.name+'.txt'):
    os.remove('sample_image/'+args.name+'.txt')

if args.aori == 'avi':
    cap = cv2.VideoCapture('sample_image/'+args.name+'.avi')
    kk = 0
    while(cap.isOpened()):
        print(kk)
        kk += 1
        ret, oriImg = cap.read()
    
        if oriImg is None:
            break
    
        rows, cols, channels = oriImg.shape
        SCALE = args.scale #120.0/rows
        oriImg = cv2.resize(oriImg, (int(SCALE*cols), int(SCALE*rows)), interpolation=cv2.INTER_CUBIC)
    
        imageToTest = Variable(T.transpose(T.transpose(T.unsqueeze(torch.from_numpy(oriImg).float(),0),2,3),1,2),volatile=True).cuda()
        multiplier = [x * model_['boxsize'] / oriImg.shape[0] for x in param_['scale_search']]
        heatmap_avg = torch.zeros((len(multiplier),19,oriImg.shape[0], oriImg.shape[1])).cuda()
    
        for m in range(len(multiplier)):
            scale = multiplier[m]
            h = int(oriImg.shape[0]*scale)
            w = int(oriImg.shape[1]*scale)
            pad_h = 0 if (h%model_['stride']==0) else model_['stride'] - (h % model_['stride'])
            pad_w = 0 if (w%model_['stride']==0) else model_['stride'] - (w % model_['stride'])
            new_h = h+pad_h
            new_w = w+pad_w
            imageToTest = cv2.resize(oriImg, (0,0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            imageToTest_padded, pad = util.padRightDownCorner(imageToTest, model_['stride'], model_['padValue'])
            imageToTest_padded = np.transpose(np.float32(imageToTest_padded[:,:,:,np.newaxis]), (3,2,0,1))/256 - 0.5
            feed = Variable(T.from_numpy(imageToTest_padded)).cuda()
            output1,output2 = model(feed)
            heatmap = nn.UpsamplingBilinear2d((oriImg.shape[0], oriImg.shape[1])).cuda()(output2)
            heatmap_avg[m] = heatmap[0].data
    
        heatmap_avg = T.transpose(T.transpose(T.squeeze(T.mean(heatmap_avg, 0)),0,1),1,2).cuda()
        heatmap_avg = heatmap_avg.cpu().numpy()
        all_peaks = []
        peak_counter = 0
    
        f = open('sample_image/'+args.name+'.txt','a+')
        for part in range(18):
            map_ori = heatmap_avg[:,:,part]
            map = gaussian_filter(map_ori, sigma=3)
    
            peak_0, peak_1 = divmod(np.argmax(map),oriImg.shape[1])
    
            f.write(str(peak_0+1)+' '+str(peak_1+1)+' ')
        f.write('\n')
        f.close()
    
    cap.release()
    
if args.aori == 'jpg':
    oriImg = cv2.imread('sample_image/'+args.name+'.jpg')

    rows, cols, channels = oriImg.shape
    SCALE = args.scale #120.0/rows
    oriImg = cv2.resize(oriImg, (int(SCALE*cols), int(SCALE*rows)), interpolation=cv2.INTER_CUBIC)

    imageToTest = Variable(T.transpose(T.transpose(T.unsqueeze(torch.from_numpy(oriImg).float(),0),2,3),1,2),volatile=True).cuda()
    multiplier = [x * model_['boxsize'] / oriImg.shape[0] for x in param_['scale_search']]
    heatmap_avg = torch.zeros((len(multiplier),19,oriImg.shape[0], oriImg.shape[1])).cuda()

    for m in range(len(multiplier)):
        scale = multiplier[m]
        h = int(oriImg.shape[0]*scale)
        w = int(oriImg.shape[1]*scale)
        pad_h = 0 if (h%model_['stride']==0) else model_['stride'] - (h % model_['stride'])
        pad_w = 0 if (w%model_['stride']==0) else model_['stride'] - (w % model_['stride'])
        new_h = h+pad_h
        new_w = w+pad_w
        imageToTest = cv2.resize(oriImg, (0,0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        imageToTest_padded, pad = util.padRightDownCorner(imageToTest, model_['stride'], model_['padValue'])
        imageToTest_padded = np.transpose(np.float32(imageToTest_padded[:,:,:,np.newaxis]), (3,2,0,1))/256 - 0.5
        feed = Variable(T.from_numpy(imageToTest_padded)).cuda()
        output1,output2 = model(feed)
        heatmap = nn.UpsamplingBilinear2d((oriImg.shape[0], oriImg.shape[1])).cuda()(output2)
        heatmap_avg[m] = heatmap[0].data

    heatmap_avg = T.transpose(T.transpose(T.squeeze(T.mean(heatmap_avg, 0)),0,1),1,2).cuda()
    heatmap_avg = heatmap_avg.cpu().numpy()
    all_peaks = []
    peak_counter = 0

    f = open('sample_image/'+args.name+'.txt','a+')
    for part in range(18):
        map_ori = heatmap_avg[:,:,part]
        map = gaussian_filter(map_ori, sigma=3)

        peak_0, peak_1 = divmod(np.argmax(map),oriImg.shape[1])

        f.write(str(peak_0+1)+' '+str(peak_1+1)+' ')
    f.write('\n')
    f.close()
