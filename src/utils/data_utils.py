import time
import numpy as np
import random
import os
import argparse
from joblib import Parallel, delayed
import scipy.misc
from misc_utils import (load_scan, get_pixels_hu, resample, segment_lung_mask, 
                        erode, reconstruct, regional_maxima, centroids_calc)
from scipy import ndimage

import matplotlib.pyplot as plt

def create_test_dataset(data_dir, AUG):
    NSL = 5 #Number of slices (pathways) for multi-way network

    files = os.listdir(data_dir)
    files.sort()

    f = np.load(os.path.join(data_dir, files[0]))
    """
    f['arr_0'] = data
    f['arr_1'] = scores
    f['arr_2'] = patient name
    f['arr_3'] = mosaic
    """
    data = np.transpose(f['arr_0'], (2, 1, 3, 0))
    data_train = data[:,:,:,0:NSL]
   
    #plt.imshow(data_train[:,:,12,0])
    #plt.show()

    label_train = np.load('src/ISBI_train_label.npy')
    scores_train = f['arr_1'][0:NSL]
    data_train = np.expand_dims(data_train, axis=4)
    scores_train = np.expand_dims(scores_train, axis=0)

    idxp = range(0, 59, 2)
    idxi = range(1, 60, 2)
    label_train = label_train[idxp]

    for ff in range(len(files)-1):
        start_time = time.time()
        filename = os.path.join(data_dir, files[ff+1])
        f = np.load(filename)
        data = np.transpose(f['arr_0'], (2, 1, 3, 0))
        scores = f['arr_1']
        data = np.expand_dims(data, axis=4)
        scores = np.expand_dims(scores, axis=0)
        data_train = np.append(data_train, data[:,:,:,0:NSL], axis=4)
        scores_train = np.append(scores_train, scores[:,0:NSL], axis=0)
    return data_train, label_train    

def create_candidate_slices(vol_dir, cand_dir, slid_dir):
    files = os.listdir(cand_dir)
    sz = 12 #size of slice (sz*2,sz*2,sz*2: 24 x 24 x 24)
    for f in range(len(files)):
        start_time = time.time()
        vol = np.load(os.path.join(vol_dir, files[f]))
        centroids = np.load(os.path.join(cand_dir, files[f]))
        szcen = len(centroids)
        if len(np.shape(centroids)) > 1:
            tz, tx, ty = np.shape(vol)
            I = []
            candsx = centroids[:,1]
            candsy = centroids[:,2]
            candsz = centroids[:,0]
            good = np.where(np.logical_and(np.logical_and(candsx > sz , (tx - candsx) > sz) ,
                 np.logical_and(np.logical_and(candsy > sz , (ty - candsy) > sz) ,
                 np.logical_and(candsz > sz , (tz - candsz) > sz))))
            centroids = centroids[good,:]
            centroids = centroids.reshape(np.shape(centroids)[1],np.shape(centroids)[2])
            for k in range(len(centroids)):
                 im = []
                 for l in range(-sz,sz):
                     im1 = vol[int(centroids[k,0]+l),
                              int(centroids[k,1]-sz) : int(sz+centroids[k,1]),
                              int(centroids[k,2]-sz) : int(sz+centroids[k,2])]
                     im.extend([im1])
                 im = np.asarray(im)
                 im = np.swapaxes(im,0,2)
                 I.extend([im])
            slides = np.asarray(I)
            out_name = os.path.join(slid_dir, files[f][:-4])
            np.save(out_name, slides)
            print('  subject: %d/%d (%.2fs)'%(f+1, len(files), time.time() - start_time))

def candidate_extraction(vol_dir, cand_dir):
    files = os.listdir(vol_dir)
    for f in range(len(files)):
        start_time = time.time()
        pix_resampled = np.load(os.path.join(vol_dir, files[f]))
        # lung extraction
        segmented_lungs_fill = segment_lung_mask(pix_resampled, True)
        extracted_lungs = pix_resampled * segmented_lungs_fill
        minv = np.min(extracted_lungs)
        extracted_lungs = extracted_lungs - minv
        extracted_lungs[extracted_lungs == -minv] = 0
        # filtering
        filtered_vol = ndimage.median_filter(extracted_lungs, 3)
        # opening by reconstruction
        marker = erode(filtered_vol, [3,3,3]) # 3D grey erosion
        op_reconstructed = reconstruct(marker, filtered_vol) # 3D grey reconstruction
        regional_max = regional_maxima(op_reconstructed) # Regional maxima
        # Computed centroids and centroids from annotations
        centroids, nconncomp = centroids_calc(regional_max) # Computed centroids
        np.save(os.path.join(cand_dir, files[f][:-4]), centroids)
        print('  subject: %d/%d (%.2fs)'%(f+1, len(files), time.time() - start_time))

def create_patients_from_dicom(dicom_dir, vols_dir):
    patients = os.listdir(dicom_dir)
    patients.sort()
    for i in range(len(patients)):
        start_time = time.time()
        subdir1 = os.listdir(os.path.join(dicom_dir, patients[i]))
        subdir1.sort()
        dcm_path, cont = os.path.join(dicom_dir, patients[i]), 0
        dcm_files_found = False
        for d in range(3): # check up to 3 cascaded folders for dcm files
            if not any(fname.endswith('.dcm') for fname in os.listdir(dcm_path)):
                dcm_path = os.path.join(dcm_path, os.listdir(dcm_path)[-1]) #to take isbi 2000 patients
                dcm_files_found = True
            else:
                break
        if not dcm_files_found: 
            print('ERROR: no dicom files found for subject %s'%(patients[i]))
            continue
        i_patient = load_scan(dcm_path)
        i_patient_pixels = get_pixels_hu(i_patient)
        pix_resampled, spacing = resample(i_patient_pixels, i_patient, [1.26,.6929,.6929]) 
        filename = os.path.join(vols_dir, patients[i] + '_2000')
        np.save(filename, pix_resampled)
        print('  subject: %d/%d (%.2fs)'%(i+1, len(patients), time.time() - start_time))

