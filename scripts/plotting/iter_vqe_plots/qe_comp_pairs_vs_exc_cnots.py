import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import ast
import pandas
import numpy

from mpl_toolkits.axes_grid1.inset_locator import zoomed_inset_axes
from mpl_toolkits.axes_grid1.inset_locator import mark_inset
from matplotlib.ticker import (MultipleLocator, FormatStrFormatter,
                               AutoMinorLocator)

if __name__ == "__main__":

    lih_db_pairs = pandas.read_csv('../../../results/iter_vqe_results/vip/LiH_g_adapt_gsdqe_comp_pairs_14-Sep-2020.csv')
    lih_db_pairs_r3 = pandas.read_csv('../../../results/iter_vqe_results/LiH_iqeb_n=1_gsdqe_r=3_03-Dec-2020.csv')
    lih_db_exc = pandas.read_csv('../../../results/iter_vqe_results/vip/LiH_g_adapt_gsdqe_comp_exc_19-Sep-2020.csv')
    lih_db_exc_r3 = pandas.read_csv('../../../results/iter_vqe_results/LiH_adapt_comp_q_exc_r=3_17-Mar-2021.csv')

    beh2_db_exc = pandas.read_csv('../../../results/iter_vqe_results/BeH2_adapt_comp_q_exc_r=1316_17-Mar-2021.csv')
    beh2_db_pairs = pandas.read_csv('../../../results/iter_vqe_results/BeH2_iqeb_q_exc_n=1_r=1316_17-Mar-2021.csv')
    beh2_db_pairs_r3 = pandas.read_csv('../../../results/iter_vqe_results/BeH2_iqeb_n=1_gsdqe_r=3_05-Dec-2020.csv')
    beh2_db_exc_r3 = pandas.read_csv('../../../results/iter_vqe_results/BeH2_adapt_comp_q_exc_r=3_17-Mar-2021.csv')

    fig, ax = plt.subplots()

    df_col = 'cnot_count'
    linewidth = 0.4
    marker = '_'

    # ax.plot(lih_db_pairs[df_col], lih_db_pairs['error'], label=r'2 parameters, $r=1.546 \AA$', marker=marker, linewidth=linewidth, color='blue')
    # ax.plot(lih_db_exc[df_col], lih_db_exc['error'], label='1 parameter, $r=1.546 \AA$', marker=marker, linewidth=linewidth, color='red')
    # ax.plot(lih_db_pairs_r3[df_col], lih_db_pairs_r3['error'], label='2 parameters, $r=3 \AA$', marker=marker, linewidth=linewidth, color='darkblue')
    # ax.plot(lih_db_exc_r3[df_col], lih_db_exc_r3['error'], label='1 parameter, $r=3 \AA$', marker=marker, linewidth=linewidth, color='darkred')


    ax.plot(beh2_db_pairs[df_col], beh2_db_pairs['error'], label=r'2 parameters, $r=1.316 \AA$', marker=marker, linewidth=linewidth, color='blue')
    ax.plot(beh2_db_exc[df_col], beh2_db_exc['error'], label='1 parameter, $r=1.316 \AA$', marker=marker, linewidth=linewidth, color='red')
    ax.plot(beh2_db_pairs_r3[df_col], beh2_db_pairs_r3['error'], label='2 parameters, $r=3 \AA$', marker=marker, linewidth=linewidth, color='darkblue')
    ax.plot(beh2_db_exc_r3[df_col], beh2_db_exc_r3['error'], label='1 parameter, $r=3 \AA$', marker=marker, linewidth=linewidth, color='darkred')

    ax.fill_between([0, 11000], 1e-15, 1e-3, color='lavender', label='chemical accuracy')

    ax.set_xlabel('Number of CNOTs')
    ax.set_ylabel(r'$E(\theta) - E_{FCI}$, Hartree')
    # ax.set_ylim(1e-9, 1e-1)
    ax.set_ylim(1e-9, 1e-0)
    # ax.set_xlim(0, 1200)
    ax.set_xlim(0, 3000)
    ax.set_yscale('log')
    ax.grid(b=True, which='major', color='grey', linestyle='--',linewidth=0.5)

    ax.legend(loc=1)#, bbox_to_anchor=(1,0.4))

    plt.show()

    print('macaroni')
