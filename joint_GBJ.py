#!/usr/local/bin/python2.7
# encoding: utf-8
'''
joint_GBJ 

@author:     zhao_lab

@copyright:  2017 organization_name. All rights reserved.

@license:    license

@contact:    zhao_lab at Yale
@deffield    updated: Updated
'''
import readline
import sys
import os
import numpy as np
import pandas as pd
import sqlite3
from fileinput import filename
from sys import argv
import rpy2
from rpy2.robjects.packages import importr
from rpy2.robjects import r
import rpy2.robjects.packages as rpackages
from rpy2.robjects.numpy2ri import numpy2ri
from rpy2.rinterface import RRuntimeError
import logging
import metax.Logging as Logging


# function of creating connection
def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :return: Connection object or None
    """
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except sqlite3.Error as e:
        print(e)
        sys.exit(1)
    return None

# function of matching two lists
def match_list(a, b):
    """ find the indices of matching element 
    :param  a: list a 
            b: list b
    :return: The indices of elements in list a in list b 
    """
    return np.array([ b.index(x) if x in b else -1 for x in a ])

# install r packages
def r_requirement():
    """ Install the required R packages
    """
    utils = rpackages.importr('utils')
    # select a mirror for R packages
    utils.chooseCRANmirror(ind=1) # select the first mirror in the list

    # install R packages     
    importr_try("GBJ")
    # multiple packages installation
    # from rpy2.robjects.vectors import StrVector 
    # if len(package_name) > 0:
    #     utils.install_packages(StrVector(package_name))

def importr_try(pkgname):
    """ Load the R packages
    :param  pkgname: the name of the package
    """
    utils = rpackages.importr('utils')
    try:
        rpack = importr(pkgname)
    except RRuntimeError:
        utils.install_packages(pkgname)
        rpack = importr(pkgname)
    return rpack    

def run(args):
    """ Main function 
    :param  args: args from the command line
    """
    # argument reading
    # index of starting task
    nstart = int(args.start_gene_index)
    
    # index of ending task
    nend = int(args.end_gene_index)
    
    # single mask dir
    single_mask_dir = args.input_folder
    
    # info file
    info_file = args.gene_info
    
    # database dir
    db_dir = args.weight_db
    
    # covariance dir 
    cov_dir = args.cov_dir
    
    # output dir 
    out_dir = args.output_dir
     
    # read list of genes
    gene_info = pd.read_table(info_file)
    
    # output name
    output_name = args.output_name 
    
    # r interface
    r_requirement()
    rpy2.robjects.numpy2ri.activate()
    importr("GBJ")
    
    P = nend - nstart + 1
    gene_ensg = gene_info["gene_ensg"].copy()
    gene_id = gene_info["gene_ensg"].copy()
    gene_name = gene_info["gene_ensg"].copy()
    
    # read z-score file
    logging.info("Read in z-score files")
    
    # directory of z-score
    os.chdir(single_mask_dir) 
    
    # search for files ending with .csv
    fi = []
    
    for file in sorted(os.listdir(single_mask_dir)):
        if file.endswith(".csv"):
            fi.append(file)
    logging.info(str(len(fi)) + " files in total.")
    N = len(fi)    
    zscore_dict = {}
    for i in range(N):
        nam = "zscore_" + str(i+1)
        zscore_dict[nam] = pd.read_csv(fi[i], header = "infer")
    
    
    # output file: list of test score and p-value
    logging.info("compute p-value for genes")
    #directory of db
    os.chdir(db_dir) 
    # initialize the outcome matrix
    outcome = pd.DataFrame(np.zeros(shape =(P,48)))
    outcome.loc[:,0] = gene_id[(nstart-1):nend]
    outcome.loc[:,1] = gene_name[(nstart-1):nend]
    outcome = outcome.rename(columns={0:"gene_id",1:"gene_name"})
   
    # read the database 
    fi = []
    for file in sorted(os.listdir(db_dir)):
        if file.endswith(".db"):
            fi.append(file)
            
    # calculation        
    for k in range(P):
        logging.info("Gene: " + str(k + nstart))
        gene = gene_ensg[k + nstart -1]
        print(gene)
        #read snp list
        #snp_rsid
        
        try:
            filename = cov_dir + "/"+ gene + ".snplist"
            snp_rsid = pd.read_table(filename, header = None)
        except:
            continue
        snp_rsid = list(snp_rsid.loc[:,0])
        
        #matrix of weights
        M = len(snp_rsid) #number of snps
        logging.info("Number of SNPs: " + str(M))
        weights = np.zeros(shape = (M, N))
        for i in range(N):
            #logging.info("Database: " + str(i+1))
            dbname = fi[i]
            conn = create_connection(dbname)
            cur = conn.cursor()  
            sql_q = 'select * from weights where gene = "' + gene + '"'
            tmp_query = cur.execute(sql_q).fetchall()
            rsid_in_db = list(map(lambda x: str(x[0]), tmp_query))
            #rsid_in_db = map(lambda x: str(x[0]), tmp_query)
            index = match_list(rsid_in_db, snp_rsid)
            indi = index[index > -1]
            # extract the weight
            sql_q = 'select * from weights where gene = "' + gene + '"'
            tmp_query = cur.execute(sql_q).fetchall()
            tmp_weights = np.array(list(map(lambda x: str(x[2]), tmp_query)))
            #tmp_weights = np.array(map(lambda x: str(x[2]), tmp_query))
            if sum(index > -1) > 0:
                weights[indi,i] = tmp_weights[index > -1]
            
        # covariance matrix of snps
        cov_file = cov_dir + "/" + gene_id[k + nstart - 1] + ".cov"
        cov_matrix = np.loadtxt(cov_file)
 
        # covariance matrix of gene in different tissue
        cov_gene = np.mat(weights.T) * np.mat(cov_matrix) * np.mat(weights)
        cov_gene = np.array(cov_gene)

        # normalization
        for i in range(N):
            if cov_gene[i,i] != 0:
                cov_gene[i,:] = cov_gene[i,:] / np.sqrt(cov_gene[i,i])
                cov_gene[:,i] = cov_gene[:,i] / cov_gene[i,i]
        
        #z-score of gene in different tissue
        zscore_gene = np.full([N, 1], np.nan)   
        for i in range(N):
            nam = "zscore_" + str(i+1)
            index = zscore_dict[nam]["gene"] == gene
            if sum(index) > 0:
                zscore_gene[i] = zscore_dict[nam]["zscore"][index].values[0]
                #p-value
                outcome.loc[k, (i+4)] = float(zscore_dict[nam]["pvalue"][index].values[0])
                  
        #only keep tissues with prediction model for gene
        index = np.isnan(zscore_gene) == False
        indext = index.T[0]
        if sum(index) > 0:
            zscore_gene = zscore_gene[index]
            cov_gene = cov_gene[indext,:][:,indext]
        else:
            # test cannot be done
            continue
        # check if the matrix is symmetric
        if np.allclose(cov_gene,cov_gene.T):
            # GBJ
            # convert the python object to r object
            r_zscore_gene = r.matrix(zscore_gene)
            r_cov_gene = r.matrix(cov_gene, nrow = cov_gene.shape[0])
            # run the test            
            GBJ_res = r["GBJ"](test_stats=r_zscore_gene, cor_mat=r_cov_gene)
            # output the test result to the result matrix
            outcome.loc[k, 2] = GBJ_res.rx2("GBJ")[0]
            print(GBJ_res.rx2("GBJ")[0])
            outcome.loc[k, 3] = GBJ_res.rx2("GBJ_pvalue")[0]
            print(GBJ_res.rx2("GBJ_pvalue")[0])
    # output the results
    os.chdir(out_dir)
    filename = output_name + "_" + str(nstart) + "_" + str(nend) + ".txt"
    outcome.to_csv(filename, header=None, index=None, sep='\t', mode='w')
    

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Build correlations and/or covariances from PHASE3 data and weights database.')

    parser.add_argument("--verbosity",
                        help="Log verbosity level. 1 is everything being logged. 10 is only high level messages, above 10 will hardly log anything",
                        default = "10")

    parser.add_argument("--weight_db",
                        help="name of weight db in data folder",
                        default="/ysm-gpfs/home/zy92/scratch60/database_tissue/")

    parser.add_argument("--output_dir",
                        help="the output directory",
                        default="/ysm-gpfs/home/zy92/scratch60/test_database/outcome/")
    
    parser.add_argument("--cov_dir",
                        help="the covariance directory",
                        default="/ysm-gpfs/home/zy92/project/metaxcan/MetaXcan/software/covariance/results5")

    parser.add_argument("--input_folder",
                        help="name of folder containing summary data",
                        default="/ysm-gpfs/pi/zhao/ml2376/association_v3/AD/single_mask")
    
    parser.add_argument("--gene_info",
                        help="name of folder containing gene list",
                        default="/ysm-gpfs/home/zy92/project/metaxcan/createdb/genelist/gene_info.txt")
    
    parser.add_argument("--start_gene_index",
                        help="index of the starting gene",
                        default=1)
    
    parser.add_argument("--end_gene_index",
                        help="index of the ending gene",
                        default=100)
    
    parser.add_argument("--output_name",
                        help="the name of output file",
                        default="Outcome")

   

    args = parser.parse_args()
    Logging.configureLogging(int(args.verbosity))
    # run the main function
    run(args)
    



