/*******************************************************************************
 *  Copyright (C) 2024 Intel Corporation
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing,
 *  software distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions
 *  and limitations under the License.
 *
 *
 *  SPDX-License-Identifier: Apache-2.0
 ******************************************************************************/


#ifndef _TOFINO_BF_PAL_DEV_INTF_H
#define _TOFINO_BF_PAL_DEV_INTF_H

#include <bf_types/bf_types.h>
#include <dvm/bf_drv_intf.h>
#include <dvm/bf_drv_profile.h>

/**
 * @brief Indicate the start of the warm init
 *
 * @param[in] dev_id Device identifier (0..BF_MAX_DEV_COUNT-1)
 * @param[in] warm_init_mode See various supported mode at bf_dev_init_mode_t
 * @param[in] serdes_upgrade_mode Specify if serdes firmware upgrade is needed
 * or not
 * @param[in] upgrade_agents Agents will be deinited
 *
 * @return BF_SUCCESS if success
 *
 * @see bf_switchd_warm_init_begin for more details
 * @see bf_pal_device_warm_init_end to end the warm init
 */
bf_status_t bf_pal_device_warm_init_begin(
    bf_dev_id_t dev_id,
    bf_dev_init_mode_t warm_init_mode,
    bf_dev_serdes_upgrade_mode_t serdes_upgrade_mode,
    bool upgrade_agents);

/**
 * @brief Device add
 *
 * @param[in] dev_id Device identifier (0..BF_MAX_DEV_COUNT-1)
 * @param[in] device_profile Specify profile see bf_device_profile_t
 *
 * @return BF_SUCCESS if success
 */
bf_status_t bf_pal_device_add(bf_dev_id_t dev_id,
                              bf_device_profile_t *device_profile);

/**
 * @brief Indicate the warm init end
 *
 * @param[in] dev_id Device identifier (0..BF_MAX_DEV_COUNT-1)
 *
 * @return BF_SUCCESS if success
 */
bf_status_t bf_pal_device_warm_init_end(bf_dev_id_t dev_id);

bf_status_t bf_pal_pltfm_reset_config(bf_dev_id_t dev_id);

/**
 * @brief Set error state to dvm
 *
 * @param[in] dev_id Device identifier (0..BF_MAX_DEV_COUNT-1)
 * @param[in] state The error state of warm init
 *
 * @return BF_SUCCESS if success
 *
 */
bf_status_t bf_pal_warm_init_error_set(bf_dev_id_t dev_id, bool state);

/**
 * @brief Get error state from dvm
 *
 * @param[in] dev_id Device identifier (0..BF_MAX_DEV_COUNT-1)
 * @param[out] state The error state of warm init
 *
 * @return BF_SUCCESS if success
 */
bf_status_t bf_pal_warm_init_error_get(bf_dev_id_t dev_id, bool *state);

// Below callbacks are local to bf-switchd
typedef bf_status_t (*bf_pal_device_warm_init_begin_fn)(
    bf_dev_id_t dev_id,
    bf_dev_init_mode_t warm_init_mode,
    bf_dev_serdes_upgrade_mode_t serdes_upgrade_mode,
    bool upgrade_agents);

typedef bf_status_t (*bf_pal_device_reset_config_fn)(bf_dev_id_t dev_id);

typedef bf_status_t (*bf_pal_device_add_fn)(
    bf_dev_id_t dev_id, bf_device_profile_t *device_profile);

typedef bf_status_t (*bf_pal_device_warm_init_end_fn)(bf_dev_id_t dev_id);
typedef bf_status_t (*bf_pal_device_cpuif_netdev_name_get_fn)(
    bf_dev_id_t dev_id, char *cpuif_netdev_name, size_t cpuif_name_size);
typedef bf_status_t (*bf_pal_device_cpuif_10g_netdev_name_get_fn)(
    bf_dev_id_t dev_id,
    char *pci_bus_dev,
    int inst,
    char *cpuif_netdev_name,
    size_t cpuif_name_size);

typedef bf_status_t (*bf_pal_device_pltfm_type_get_fn)(bf_dev_id_t dev_id,
                                                       bool *is_sw_model);

typedef bf_status_t (*bf_pal_warm_init_error_set_fn)(bf_dev_id_t dev_id,
                                                     bool state);

typedef bf_status_t (*bf_pal_warm_init_error_get_fn)(bf_dev_id_t dev_id,
                                                     bool *state);

typedef struct bf_pal_dev_callbacks_s {
  bf_pal_device_warm_init_begin_fn warm_init_begin;
  bf_pal_device_add_fn device_add;
  bf_pal_device_warm_init_end_fn warm_init_end;
  bf_pal_device_cpuif_netdev_name_get_fn cpuif_netdev_name_get;
  bf_pal_device_cpuif_10g_netdev_name_get_fn cpuif_10g_netdev_name_get;
  bf_pal_device_pltfm_type_get_fn pltfm_type_get;
  bf_pal_device_reset_config_fn reset_config;
  bf_pal_warm_init_error_set_fn warm_init_error_set;
  bf_pal_warm_init_error_get_fn warm_init_error_get;
} bf_pal_dev_callbacks_t;

bf_status_t bf_pal_device_callbacks_register(bf_pal_dev_callbacks_t *callbacks);
bf_status_t bf_pal_cpuif_netdev_name_get(bf_dev_id_t dev_id,
                                         char *cpuif_netdev_name,
                                         size_t cpuif_name_size);
bf_status_t bf_pal_cpuif_10g_netdev_name_get(bf_dev_id_t dev_id,
                                             char *pci_bus_dev,
                                             int instance,
                                             char *cpuif_netdev_name,
                                             size_t cpuif_name_size);
#endif
