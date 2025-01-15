################################################################################
 #  Copyright (C) 2024 Intel Corporation
 #
 #  Licensed under the Apache License, Version 2.0 (the "License");
 #  you may not use this file except in compliance with the License.
 #  You may obtain a copy of the License at
 #
 #  http://www.apache.org/licenses/LICENSE-2.0
 #
 #  Unless required by applicable law or agreed to in writing,
 #  software distributed under the License is distributed on an "AS IS" BASIS,
 #  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 #  See the License for the specific language governing permissions
 #  and limitations under the License.
 #
 #
 #  SPDX-License-Identifier: Apache-2.0
################################################################################

"""
Base classes for test cases

Tests will usually inherit from one of these classes to have the controller
and/or dataplane automatically set up.
"""

import os

from collections import OrderedDict

import ptf
from ptf import config
from ptf.base_tests import BaseTest
from ptf.packet import *

from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol

import sai_thrift.sai_rpc as sai_rpc

# Import both adapter module and all its functions
import sai_adapter as adapter
from sai_utils import *

################################################################
#
# Thrift interface base tests
#
################################################################

ROUTER_MAC = '00:77:66:55:44:00'


class ThriftInterface(BaseTest):
    """
    The class gets and formats a port map and creates an RPC client.

    Sets the following class attributes:
        self.transport
        self.protocol
        self.client
        self.test_params

    Removes objects created in setup
    """

    def loadPortMap(self):
        """
        Method to get and format portmap
        """
        if self.port_map_loaded:
            print('port_map already loaded')
            return

        if "port_map" in self.test_params:
            user_input = self.test_params['port_map']
            splitted_map = user_input.split(",")
            for item in splitted_map:
                interface_front_pair = item.split("@")
                self.interface_to_front_mapping[interface_front_pair[0]] =  \
                    interface_front_pair[1]
        elif "port_map_file" in self.test_params:
            user_input = self.test_params['port_map_file']
            map_file = open(user_input, 'r')
            for line in map_file:
                if (line and (
                        line[0] == '#' or line[0] == ';' or line[0] == '/')):
                    continue
                interface_front_pair = line.split("@")
                self.interface_to_front_mapping[interface_front_pair[0]] =  \
                    interface_front_pair[1].strip()

        self.port_map_loaded = True

    def createRpcClient(self):
        """
        Set up thrift client and contact server
        """

        if "thrift_server" in self.test_params:
            server = self.test_params['thrift_server']
        else:
            server = 'localhost'

        self.transport = TSocket.TSocket(server, 9092)
        self.transport = TTransport.TBufferedTransport(self.transport)
        self.protocol = TBinaryProtocol.TBinaryProtocol(self.transport)

        self.client = sai_rpc.Client(self.protocol)
        self.transport.open()

    def setUp(self):
        self.interface_to_front_mapping = {}
        self.port_map_loaded = False
        BaseTest.setUp(self)
        self.test_params = test_params_get()
        self.loadPortMap()
        self.createRpcClient()

    def tearDown(self):
        BaseTest.tearDown(self)
        self.transport.close()


class ThriftInterfaceDataPlane(ThriftInterface):
    """
    Root class that sets up the thrift interface and dataplane
    """

    def removeCpuPort(self):
        """
        Remove CPU port from port map
        """
        test_params = test_params_get()
        for _, port, _ in config["interfaces"]:
            if test_params['arch'] == "tofino2":
                if port == 320:
                    continue
                if port == 2:
                    self.dataplane.port_remove(0, port)
                    ptf.config["port_map"].pop((0, port), None)
                    continue
            else:
                if port in (64, 320):
                    self.dataplane.port_remove(0, port)
                    ptf.config["port_map"].pop((0, port), None)
                    continue

    def setUp(self):
        ThriftInterface.setUp(self)
        self.dataplane = ptf.dataplane_instance
        self.removeCpuPort()
        if self.dataplane is not None:
            self.dataplane.flush()
            if config["log_dir"] is not None:
                filename = os.path.join(config["log_dir"], str(self)) + ".pcap"
                self.dataplane.start_pcap(filename)

    def tearDown(self):
        if config["log_dir"] is not None:
            self.dataplane.stop_pcap()
        ThriftInterface.tearDown(self)


def parse_port_config(port_config_file):
    '''
    Parses port_config.ini file.

    Example of supported format for port_config.ini:
    # name          lanes         alias       index    speed    autoneg   fec
    Ethernet0         0           Ethernet0       1    25000      off     none
    Ethernet1         1           Ethernet1       1    25000      off     none
    Ethernet2         2           Ethernet2       1    25000      off     none
    Ethernet3         3           Ethernet3       1    25000      off     none
    Ethernet4         4           Ethernet4       2    25000      off     none
    Ethernet5         5           Ethernet5       2    25000      off     none
    Ethernet6         6           Ethernet6       2    25000      off     none
    Ethernet7         7           Ethernet7       2    25000      off     none
    Ethernet8         8           Ethernet8       3    25000      off     none
    Ethernet9         9           Ethernet9       3    25000      off     none
    Ethernet10        10          Ethernet10      3    25000      off     none
    Ethernet11        11          Ethernet11      3    25000      off     none
    etc

    Args:
        port_config_file (string): path to port config file

    Returns:
        dict: port configuation from file

    Raises:
        e: exit if file not found
    '''
    ports = OrderedDict()
    try:
        with open(port_config_file) as conf:
            for line in conf:
                if line.startswith('#'):
                    if "name" in line:
                        titles = line.strip('#').split()
                    continue
                tokens = line.split()
                if len(tokens) < 2:
                    continue
                name_index = titles.index('name')
                name = tokens[name_index]
                data = {}
                for i, item in enumerate(tokens):
                    if i == name_index:
                        continue
                    data[titles[i]] = item
                data['lanes'] = [int(lane)
                                 for lane in data['lanes'].split(',')]
                data['speed'] = int(data['speed'])
                ports[name] = data
        return ports
    except Exception as e:
        raise e


class SaiHelperBase(ThriftInterfaceDataPlane):
    '''
    SAI test helper base class without initial common switch setup.

    Sets the following class attributes:
        self.default_vlan_id
        self.default_stp
        self.default_vrf
        self.default_1q_bridge
        self.cpu_port_hdl
        self.acl_stage_ingress
        self.self.acl_stage_egress
        self.default_trap_group
        self.active_ports - number of active ports
        self.port_list - list of all active port objects
        self.portX objects for all active ports
    '''

    def setUp(self):
        ThriftInterfaceDataPlane.setUp(self)
        self.getSwitchPorts()

        if 'switch_id' in self.test_params:
            # Get switch id initialized before
            self.switch_id = self.test_params['switch_id']
        else:
            # Initialize switch
            self.switch_id = sai_thrift_create_switch(
                self.client, init_switch=True, src_mac_address=ROUTER_MAC)
            self.assertEqual(self.status(), SAI_STATUS_SUCCESS)
            self.test_params['switch_id'] = self.switch_id

        self.saveNumberOfAvaiableResources()

        # get default vlan
        attr = sai_thrift_get_switch_attribute(
            self.client, default_vlan_id=True)
        self.default_vlan_id = attr['default_vlan_id']

        # get default stp
        attr = sai_thrift_get_switch_attribute(
            self.client, default_stp_inst_id=True)
        self.default_stp = attr['default_stp_inst_id']

        if 'port_config_ini' in self.test_params:
            if 'createPorts_has_been_called' not in config:
                self.createPorts()
                # check if ports became UP
                # self.checkPortsUp()
                config['createPorts_has_been_called'] = 1

        # get number of active ports
        attr = sai_thrift_get_switch_attribute(
            self.client, number_of_active_ports=True)
        self.active_ports = attr['number_of_active_ports']

        # get port list
        attr = sai_thrift_get_switch_attribute(
            self.client, port_list=sai_thrift_object_list_t(
                idlist=[], count=self.active_ports))

        self.assertEqual(self.active_ports, attr['port_list'].count)
        self.port_list = attr['port_list'].idlist

        for index in range(0, self.active_ports):
            setattr(self, 'port%s' % index, self.port_list[index])

        # get default vrf
        attr = sai_thrift_get_switch_attribute(
            self.client, default_virtual_router_id=True)
        self.default_vrf = attr['default_virtual_router_id']
        self.assertTrue(self.default_vrf != 0)

        # get default 1Q bridge OID
        attr = sai_thrift_get_switch_attribute(
            self.client, default_1q_bridge_id=True)
        self.default_1q_bridge = attr['default_1q_bridge_id']
        self.assertTrue(self.default_1q_bridge != 0)

        # get cpu port
        attr = sai_thrift_get_switch_attribute(self.client, cpu_port=True)
        self.cpu_port_hdl = attr['cpu_port']
        self.assertTrue(self.cpu_port_hdl != 0)

        # get cpu port queue handles
        attr = sai_thrift_get_port_attribute(self.client,
                                             self.cpu_port_hdl,
                                             qos_number_of_queues=True)
        num_queues = attr["qos_number_of_queues"]
        q_list = sai_thrift_object_list_t(count=num_queues)
        attr = sai_thrift_get_port_attribute(self.client,
                                             self.cpu_port_hdl,
                                             qos_queue_list=q_list)
        for queue in range(0, num_queues):
            queue_id = attr["qos_queue_list"].idlist[queue]
            setattr(self, 'cpu_queue%s' % queue, queue_id)
            q_attr = sai_thrift_get_queue_attribute(
                self.client,
                queue_id,
                port=True,
                index=True,
                parent_scheduler_node=True)
            self.assertTrue(queue == q_attr["index"])
            self.assertTrue(self.cpu_port_hdl == q_attr["port"])

        # get ACL capability
        attr = sai_thrift_get_switch_attribute(
            self.client, max_acl_action_count=True)
        max_acl_action_count = attr['max_acl_action_count']
        s32 = sai_thrift_s32_list_t(int32list=[], count=max_acl_action_count)
        cap = sai_thrift_acl_capability_t(action_list=s32)
        attr = sai_thrift_get_switch_attribute(
            self.client, acl_stage_ingress=cap)
        self.acl_stage_ingress = \
            attr['acl_stage_ingress'].action_list.int32list
        self.assertTrue(len(self.acl_stage_ingress) != 0)
        attr = sai_thrift_get_switch_attribute(
            self.client, acl_stage_egress=cap)
        self.acl_stage_egress = attr['acl_stage_egress'].action_list.int32list
        self.assertTrue(len(self.acl_stage_egress) != 0)
        attr = sai_thrift_get_switch_attribute(
            self.client, default_trap_group=True)
        self.default_trap_group = attr['default_trap_group']
        self.assertTrue(self.default_trap_group != 0)

    def createPorts(self):
        """
        Create ports after reading from port config file
        """

        def fec_str_to_int(fec):
            """
            Convert fec string to SAI enum

            Args:
                fec (string): fec string from port_config

            Returns:
                int: SAI enum value
            """
            fec_dict = {
                'rs': SAI_PORT_FEC_MODE_RS,
                'fc': SAI_PORT_FEC_MODE_FC
            }
            return fec_dict.get(fec, SAI_PORT_FEC_MODE_NONE)

        # delete the existing ports
        attr = sai_thrift_get_switch_attribute(
            self.client, number_of_active_ports=True)
        self.active_ports = attr['number_of_active_ports']
        attr = sai_thrift_get_switch_attribute(
            self.client, port_list=sai_thrift_object_list_t(
                idlist=[], count=self.active_ports))
        if self.active_ports:
            self.port_list = attr['port_list'].idlist
            for port in self.port_list:
                sai_thrift_remove_port(self.client, port)

        # add new ports from port config file
        self.ports_config = parse_port_config(
            self.test_params['port_config_ini'])
        for name, port in self.ports_config.items():
            print("Creating port: %s" % name)
            fec_mode = fec_str_to_int(port.get('fec', None))
            auto_neg_mode = port.get('autoneg', "").lower() == "on"
            sai_list = sai_thrift_u32_list_t(
                count=len(port['lanes']), uint32list=port['lanes'])
            sai_thrift_create_port(
                self.client,
                hw_lane_list=sai_list,
                fec_mode=fec_mode,
                auto_neg_mode=auto_neg_mode,
                speed=port['speed'],
                admin_state=True)

    def checkPortsUp(self):
        '''
        Wait for all ports to be UP
        '''

        for _ in range(1, 5):
            allup = True
            for port in self.port_list:
                attr = sai_thrift_get_port_attribute(
                    self.client, port, oper_status=True)
                if attr['oper_status'] != SAI_SWITCH_OPER_STATUS_UP:
                    allup = False
                    break
            if allup:
                break
            time.sleep(10)
        self.assertTrue(allup)

    def tearDown(self):
        try:
            for port in self.port_list:
                sai_thrift_clear_port_stats(self.client, port)
                sai_thrift_set_port_attribute(
                    self.client, port, port_vlan_id=0)

            self.assertEqual(True, self.verifyNumberOfAvaiableResources(
                debug=False))

        finally:
            ThriftInterfaceDataPlane.tearDown(self)

    def getSwitchPorts(self):
        """
        Gets device port numbers
        """
        test_params = test_params_get()
        dev_no = 0
        cpu_no = 0
        for _, port, _ in config["interfaces"]:
            if test_params['arch'] == "tofino2":
                if port == 320:
                    continue
                if port == 2:
                    setattr(self, 'cpu_port%d' % cpu_no, port)
                    cpu_no += 1
                    continue
            else:
                if port in (64, 320):
                    setattr(self, 'cpu_port%d' % cpu_no, port)
                    cpu_no += 1
                    continue

            setattr(self, 'dev_port%d' % dev_no, port)
            dev_no += 1

    def printNumberOfAvaiableResources(self):
        """
        Prints numbers of available resources
        """
        try:
            print("***** Number of available resources")
            print("self.available_next_hop_group_entry=",
                  self.available_next_hop_group_entry)
            print("self.available_next_hop_group_member_entry=",
                  self.available_next_hop_group_member_entry)
            print("self.available_ipv4_nexthop_entry=",
                  self.available_ipv4_nexthop_entry)
            print("self.available_ipv6_nexthop_entry=",
                  self.available_ipv6_nexthop_entry)
            print("self.available_fdb_entry=", self.available_fdb_entry)
            print("self.available_ipv6_route_entry=",
                  self.available_ipv6_route_entry)
            print("self.available_ipv4_route_entry=",
                  self.available_ipv4_route_entry)
        finally:
            pass

    def saveNumberOfAvaiableResources(self, debug=False):
        """
        Saves numbers of available resources

        Args:
            debug (boolean): enables debug option
        """
        if debug:
            print("saveNumberOfAvaiableResources")
        try:
            attr_list = sai_thrift_get_switch_attribute(
                self.client,
                number_of_ecmp_groups=True,
                ecmp_members=True,
                available_next_hop_group_entry=True,
                available_next_hop_group_member_entry=True,
                available_ipv6_nexthop_entry=True,
                available_ipv4_nexthop_entry=True,
                available_fdb_entry=True,
                available_ipv6_route_entry=True,
                available_ipv4_route_entry=True)
            self.available_next_hop_group_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_NEXT_HOP_GROUP_ENTRY"]
            self.available_next_hop_group_member_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_NEXT_HOP_GROUP_MEMBER_ENTRY"]
            self.available_ipv4_nexthop_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV4_NEXTHOP_ENTRY"]
            self.available_ipv6_nexthop_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV6_NEXTHOP_ENTRY"]
            self.available_fdb_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_FDB_ENTRY"]
            self.available_ipv6_route_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV6_ROUTE_ENTRY"]
            self.available_ipv4_route_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV4_ROUTE_ENTRY"]
            if debug:
                self.printNumberOfAvaiableResources()
        finally:
            pass

    def verifyNumberOfAvaiableResources(self, debug=False):
        """
        Verifies numbers of available resources

        Args:
            debug (boolean): enables debug option

        Returns:
            boolean: verification result
        """
        result = True
        try:
            attr_list = sai_thrift_get_switch_attribute(
                self.client,
                number_of_ecmp_groups=True,
                ecmp_members=True,
                available_next_hop_group_entry=True,
                available_next_hop_group_member_entry=True,
                available_ipv6_nexthop_entry=True,
                available_ipv4_nexthop_entry=True,
                available_fdb_entry=True,
                available_ipv6_route_entry=True,
                available_ipv4_route_entry=True)
            available_next_hop_group_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_NEXT_HOP_GROUP_ENTRY"]
            available_next_hop_group_member_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_NEXT_HOP_GROUP_MEMBER_ENTRY"]
            available_ipv4_nexthop_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV4_NEXTHOP_ENTRY"]
            available_ipv6_nexthop_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV6_NEXTHOP_ENTRY"]
            available_fdb_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_FDB_ENTRY"]
            available_ipv6_route_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV6_ROUTE_ENTRY"]
            available_ipv4_route_entry = attr_list[
                "SAI_SWITCH_ATTR_AVAILABLE_IPV4_ROUTE_ENTRY"]

            resources_dict = {
                "available_next_hop_group_entry": [
                    available_next_hop_group_entry,
                    self.available_next_hop_group_entry],
                "available_next_hop_group_member_entry": [
                    available_next_hop_group_member_entry,
                    self.available_next_hop_group_member_entry],
                "available_ipv4_nexthop_entry": [
                    available_ipv4_nexthop_entry,
                    self.available_ipv4_nexthop_entry],
                "available_ipv6_nexthop_entry": [
                    available_ipv6_nexthop_entry,
                    self.available_ipv6_nexthop_entry],
                "available_fdb_entry": [
                    available_fdb_entry,
                    self.available_fdb_entry],
                "available_ipv6_route_entry": [
                    available_ipv6_route_entry,
                    self.available_ipv6_route_entry],
                "available_ipv4_route_entry": [
                    available_ipv4_route_entry,
                    self.available_ipv4_route_entry]}

            for key in resources_dict:
                if (resources_dict[key][0] !=
                        resources_dict[key][1]):
                    print(key, " != ", resources_dict[key][0])
                    result = False
                    break

            if debug:
                if result:
                    print("Number of resources OK")
                else:
                    print("Number of resources NOT OK")

        finally:
            pass

        return result

    @staticmethod
    def status():
        """
        Returns the last operation status.

        Returns:
            int: sai call result
        """
        return adapter.status


class SaiHelper(SaiHelperBase):
    """
    Sets common base configuration for tests

    Common configuration:
    +------------+------------+-----------+-----------+
    |    Name    |   Vlan ID  |  Ports    |  Tagging  |
    +============+============+===========+===========+
    |   vlan10   |     10     |   port0   |  untagged |
    |            |            |   port1   |    tagged |
    |            |            |    lag1   |  untagged |
    +------------+------------+-----------+-----------+
    |   vlan20   |     20     |   port2   |  untagged |
    |            |            |   port3   |    tagged |
    |            |            |    lag2   |    tagged |
    +------------+------------+-----------+-----------+
    |    lag1    |     --     |   port4   |     --    |
    |            |            |   port5   |           |
    |            |            |   port6   |           |
    +------------+------------+-----------+-----------+
    |    lag2    |     --     |   port7   |     --    |
    |            |            |   port8   |           |
    |            |            |   port9   |           |
    +------------+------------+-----------+-----------+
    | port10_rif |     --     |  port10   |     --    |
    +------------+------------+-----------+-----------+
    | port11_rif |     --     |  port11   |     --    |
    +------------+------------+-----------+-----------+
    | port12_rif |     --     |  port12   |     --    |
    +------------+------------+-----------+-----------+
    | port13_rif |     --     |  port13   |     --    |
    +------------+------------+-----------+-----------+
    |    lag3    |     --     |  port14   |     --    |
    |  lag3_rif  |            |  port15   |           |
    |            |            |  port16   |           |
    +------------+------------+-----------+-----------+
    |    lag4    |     --     |  port17   |     --    |
    |  lag4_rif  |            |  port18   |           |
    |            |            |  port19   |           |
    +------------+------------+-----------+-----------+
    |   vlan30   |     30     |  port20   |  untagged |
    | vlan30_rif |            |  port21   |    tagged |
    |            |            |    lag5   |    tagged |
    +------------+------------+-----------+-----------+
    |    lag5    |     --     |  port22   |     --    |
    |            |            |  port23   |           |
    +------------+------------+-----------+-----------+
    | Additional |     --     |  port24   |     --    |
    |    ports   |            |  port25   |           |
    |            |            |  port26   |           |
    |            |            |  port27   |           |
    |            |            |  port28   |           |
    |            |            |  port29   |           |
    |            |            |  port30   |           |
    |            |            |  port31   |           |
    +------------+------------+-----------+-----------+
    """

    def setUp(self):
        SaiHelperBase.setUp(self)

        # create bridge ports
        self.port0_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.port0,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.port0_bp != 0)
        self.port1_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.port1,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.port1_bp != 0)
        self.port2_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.port2,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.port2_bp != 0)
        self.port3_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.port3,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.port3_bp != 0)
        self.port20_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.port20,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.port20_bp != 0)
        self.port21_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.port21,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.port21_bp != 0)

        # create LAGs
        self.lag1 = sai_thrift_create_lag(self.client)
        self.assertTrue(self.lag1 != 0)
        self.lag1_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.lag1,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.lag1_bp != 0)
        self.lag1_member4 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag1, port_id=self.port4)
        self.lag1_member5 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag1, port_id=self.port5)
        self.lag1_member6 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag1, port_id=self.port6)

        self.lag2 = sai_thrift_create_lag(self.client)
        self.assertTrue(self.lag2 != 0)
        self.lag2_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.lag2,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.lag2_bp != 0)
        self.lag2_member7 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag2, port_id=self.port7)
        self.lag2_member8 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag2, port_id=self.port8)
        self.lag2_member9 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag2, port_id=self.port9)

        # L3 lags
        self.lag3 = sai_thrift_create_lag(self.client)
        self.assertTrue(self.lag3 != 0)
        self.lag3_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.lag3,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.lag3_bp != 0)
        self.lag3_member14 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag3, port_id=self.port14)
        self.lag3_member15 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag3, port_id=self.port15)
        self.lag3_member16 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag3, port_id=self.port16)

        self.lag4 = sai_thrift_create_lag(self.client)
        self.assertTrue(self.lag4 != 0)
        self.lag4_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.lag4,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.lag4_bp != 0)
        self.lag4_member17 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag4, port_id=self.port17)
        self.lag4_member18 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag4, port_id=self.port18)
        self.lag4_member19 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag4, port_id=self.port19)

        self.lag5 = sai_thrift_create_lag(self.client)
        self.assertTrue(self.lag5 != 0)
        self.lag5_bp = sai_thrift_create_bridge_port(
            self.client,
            bridge_id=self.default_1q_bridge,
            port_id=self.lag5,
            type=SAI_BRIDGE_PORT_TYPE_PORT,
            admin_state=True)
        self.assertTrue(self.lag5_bp != 0)
        self.lag5_member22 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag5, port_id=self.port22)
        self.lag5_member23 = sai_thrift_create_lag_member(
            self.client, lag_id=self.lag5, port_id=self.port23)

        # create vlan 10 with port0, port1 and lag1
        self.vlan10 = sai_thrift_create_vlan(self.client, vlan_id=10)
        self.assertTrue(self.vlan10 != 0)
        self.vlan10_member0 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan10,
            bridge_port_id=self.port0_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_UNTAGGED)
        self.vlan10_member1 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan10,
            bridge_port_id=self.port1_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_TAGGED)
        self.vlan10_member2 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan10,
            bridge_port_id=self.lag1_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_UNTAGGED)

        # create vlan 20 with port2, port3 and lag2
        self.vlan20 = sai_thrift_create_vlan(self.client, vlan_id=20)
        self.assertTrue(self.vlan20 != 0)
        self.vlan20_member0 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan20,
            bridge_port_id=self.port2_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_UNTAGGED)
        self.vlan20_member1 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan20,
            bridge_port_id=self.port3_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_TAGGED)
        self.vlan20_member2 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan20,
            bridge_port_id=self.lag2_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_TAGGED)

        # create vlan 30 with port20, port21 and lag5
        self.vlan30 = sai_thrift_create_vlan(self.client, vlan_id=30)
        self.assertTrue(self.vlan30 != 0)
        self.vlan30_member0 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan30,
            bridge_port_id=self.port20_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_UNTAGGED)
        self.vlan30_member1 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan30,
            bridge_port_id=self.port21_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_TAGGED)
        self.vlan30_member2 = sai_thrift_create_vlan_member(
            self.client,
            vlan_id=self.vlan30,
            bridge_port_id=self.lag5_bp,
            vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_TAGGED)

        # setup untagged ports
        sai_thrift_set_port_attribute(self.client, self.port0, port_vlan_id=10)
        sai_thrift_set_lag_attribute(self.client, self.lag1, port_vlan_id=10)
        sai_thrift_set_port_attribute(self.client, self.port2, port_vlan_id=20)
        sai_thrift_set_port_attribute(
            self.client, self.port20, port_vlan_id=30)

        # create L3 configuration
        self.vlan30_rif = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_VLAN,
            virtual_router_id=self.default_vrf,
            vlan_id=self.vlan30)
        self.assertTrue(self.vlan30_rif != 0)

        self.lag3_rif = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_PORT,
            virtual_router_id=self.default_vrf,
            port_id=self.lag3)
        self.assertTrue(self.lag3_rif != 0)

        self.lag4_rif = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_PORT,
            virtual_router_id=self.default_vrf,
            port_id=self.lag4)
        self.assertTrue(self.lag4_rif != 0)

        self.port10_rif = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_PORT,
            virtual_router_id=self.default_vrf,
            port_id=self.port10)
        self.assertTrue(self.port10_rif != 0)

        self.port11_rif = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_PORT,
            virtual_router_id=self.default_vrf,
            port_id=self.port11)
        self.assertTrue(self.port11_rif != 0)

        self.port12_rif = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_PORT,
            virtual_router_id=self.default_vrf,
            port_id=self.port12)
        self.assertTrue(self.port12_rif != 0)

        self.port13_rif = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_PORT,
            virtual_router_id=self.default_vrf,
            port_id=self.port13)
        self.assertTrue(self.port13_rif != 0)

    @staticmethod
    def saiWaitFdbAge(timeout):
        """ sai_wait_fdb_age() - Wait for fdb entry to ageout

        Args:
            timeout (int): Timeout value in seconds
        """
        print("Waiting for fdb entry to Age")
        aging_interval_buffer = 10
        time.sleep(timeout + aging_interval_buffer)

    def tearDown(self):
        sai_thrift_remove_router_interface(self.client, self.vlan30_rif)
        sai_thrift_remove_router_interface(self.client, self.port10_rif)
        sai_thrift_remove_router_interface(self.client, self.port11_rif)
        sai_thrift_remove_router_interface(self.client, self.port12_rif)
        sai_thrift_remove_router_interface(self.client, self.port13_rif)
        sai_thrift_remove_router_interface(self.client, self.lag3_rif)
        sai_thrift_remove_router_interface(self.client, self.lag4_rif)

        sai_thrift_set_port_attribute(self.client, self.port20, port_vlan_id=0)
        sai_thrift_set_port_attribute(self.client, self.port2, port_vlan_id=0)
        sai_thrift_set_lag_attribute(self.client, self.lag1, port_vlan_id=0)
        sai_thrift_set_port_attribute(self.client, self.port0, port_vlan_id=0)

        # remove vlan config
        sai_thrift_remove_vlan_member(self.client, self.vlan30_member2)
        sai_thrift_remove_vlan_member(self.client, self.vlan30_member1)
        sai_thrift_remove_vlan_member(self.client, self.vlan30_member0)
        sai_thrift_remove_vlan(self.client, self.vlan30)
        sai_thrift_remove_vlan_member(self.client, self.vlan20_member2)
        sai_thrift_remove_vlan_member(self.client, self.vlan20_member1)
        sai_thrift_remove_vlan_member(self.client, self.vlan20_member0)
        sai_thrift_remove_vlan(self.client, self.vlan20)
        sai_thrift_remove_vlan_member(self.client, self.vlan10_member2)
        sai_thrift_remove_vlan_member(self.client, self.vlan10_member1)
        sai_thrift_remove_vlan_member(self.client, self.vlan10_member0)
        sai_thrift_remove_vlan(self.client, self.vlan10)

        # remove lag config
        sai_thrift_remove_lag_member(self.client, self.lag5_member22)
        sai_thrift_remove_lag_member(self.client, self.lag5_member23)
        sai_thrift_remove_bridge_port(self.client, self.lag5_bp)
        sai_thrift_remove_lag(self.client, self.lag5)
        sai_thrift_remove_lag_member(self.client, self.lag4_member19)
        sai_thrift_remove_lag_member(self.client, self.lag4_member18)
        sai_thrift_remove_lag_member(self.client, self.lag4_member17)
        sai_thrift_remove_bridge_port(self.client, self.lag4_bp)
        sai_thrift_remove_lag(self.client, self.lag4)
        sai_thrift_remove_lag_member(self.client, self.lag3_member16)
        sai_thrift_remove_lag_member(self.client, self.lag3_member15)
        sai_thrift_remove_lag_member(self.client, self.lag3_member14)
        sai_thrift_remove_bridge_port(self.client, self.lag3_bp)
        sai_thrift_remove_lag(self.client, self.lag3)
        sai_thrift_remove_lag_member(self.client, self.lag2_member9)
        sai_thrift_remove_lag_member(self.client, self.lag2_member8)
        sai_thrift_remove_lag_member(self.client, self.lag2_member7)
        sai_thrift_remove_bridge_port(self.client, self.lag2_bp)
        sai_thrift_remove_lag(self.client, self.lag2)
        sai_thrift_remove_lag_member(self.client, self.lag1_member6)
        sai_thrift_remove_lag_member(self.client, self.lag1_member5)
        sai_thrift_remove_lag_member(self.client, self.lag1_member4)
        sai_thrift_remove_bridge_port(self.client, self.lag1_bp)
        sai_thrift_remove_lag(self.client, self.lag1)

        # remove bridge ports
        sai_thrift_remove_bridge_port(self.client, self.port21_bp)
        sai_thrift_remove_bridge_port(self.client, self.port20_bp)
        sai_thrift_remove_bridge_port(self.client, self.port3_bp)
        sai_thrift_remove_bridge_port(self.client, self.port2_bp)
        sai_thrift_remove_bridge_port(self.client, self.port1_bp)
        sai_thrift_remove_bridge_port(self.client, self.port0_bp)

        SaiHelperBase.tearDown(self)


class MinimalPortVlanConfig(SaiHelperBase):
    '''
    Minimal port and vlan configuration. Creates port_num bridge ports and adds
    them to VLAN with vlan_id. Configures ports as untagged.
    '''

    def __init__(self, port_num, vlan_id=100):
        '''
        Args:
            port_num (int): Number of ports to configure
            vlan_id (int): ID of VLAN that will be created
        '''
        super(MinimalPortVlanConfig, self).__init__()

        self.port_num = port_num
        self.vlan_id = vlan_id

    def setUp(self):
        super(MinimalPortVlanConfig, self).setUp()

        if self.port_num > self.active_ports:
            raise ValueError('Number of ports to configure ({}) is higher '
                             'than number of active ports ({})'.format(
                                 self.port_num, self.active_ports))

        self.bridge_port = []
        self.vlan_member = []

        # create bridge ports
        for i in range(0, self.port_num):
            bp = sai_thrift_create_bridge_port(
                self.client, bridge_id=self.default_1q_bridge,
                port_id=self.port_list[i], type=SAI_BRIDGE_PORT_TYPE_PORT,
                admin_state=True)

            self.assertGreater(bp, 0)
            self.bridge_port.append(bp)

        # create vlan
        self.vlan = sai_thrift_create_vlan(self.client, vlan_id=self.vlan_id)
        self.assertGreater(self.vlan, 0)

        # add ports to vlan
        for i in range(0, self.port_num):
            vm = sai_thrift_create_vlan_member(
                self.client, vlan_id=self.vlan,
                bridge_port_id=self.bridge_port[i],
                vlan_tagging_mode=SAI_VLAN_TAGGING_MODE_UNTAGGED)

            self.assertGreater(vm, 0)
            self.vlan_member.append(vm)

        # setup untagged ports
        for i in range(0, self.port_num):
            status = sai_thrift_set_port_attribute(
                self.client, self.port_list[i], port_vlan_id=self.vlan_id)

            self.assertEqual(status, SAI_STATUS_SUCCESS)

    def tearDown(self):
        # revert untagged ports configuration
        for i in range(0, self.port_num):
            sai_thrift_set_port_attribute(
                self.client, self.port_list[i], port_vlan_id=0)

        # remove ports from vlan
        for i in range(0, self.port_num):
            sai_thrift_remove_vlan_member(self.client, self.vlan_member[i])

        # remove vlan
        sai_thrift_remove_vlan(self.client, self.vlan)

        # remove bridge ports
        for i in range(0, self.port_num):
            sai_thrift_remove_bridge_port(self.client, self.bridge_port[i])

        super(MinimalPortVlanConfig, self).tearDown()


class SonicTopologyT1(SaiHelperBase):
    '''
    Basic configuration as used in SONiC T1 topology.
    '''

    def __init__(self):
        super(SonicTopologyT1, self).__init__()

        self.t0_neigh_num = 16
        self.t2_neigh_num = 16
        self.t1_config = {}

        self.t2_ports = []
        self.t2_ipv4_neigh = []
        self.t2_ipv6_neigh = []
        self.t2_neigh_mac = generate_mac_addresses(
            self.t2_neigh_num,
            "52:54:00:13:00:00")

    def setUp(self):
        super(SonicTopologyT1, self).setUp()

        for port_no in range(self.t2_neigh_num):
            self.t2_ports.append(getattr(self, "dev_port%d" % port_no))
            self.t2_ipv4_neigh.append("10.0.0.%d" % (port_no * 2 + 1))
            self.t2_ipv6_neigh.append("fc00::%x" % (port_no * 4 + 2))

        # SONiC T1 configuration
        self.t1_config["t2"] = {
            "rifs": {},
            "neighs": {},
            "nhgs": {},
            "nhs": {},
            "nhg_mbrs": {},
        }

        self.t1_config["t0"] = {
            "rifs": {},
        }

        # loopback RIF
        self.rif_lpb = sai_thrift_create_router_interface(
            self.client,
            type=SAI_ROUTER_INTERFACE_TYPE_LOOPBACK,
            virtual_router_id=self.default_vrf,
            mtu=9100)

        # IPv4 & IPv6 NHGs
        for idx in [0, 1]:
            self.t1_config["t2"]["nhgs"][idx] = \
                sai_thrift_create_next_hop_group(
                    self.client,
                    type=SAI_NEXT_HOP_GROUP_TYPE_DYNAMIC_UNORDERED_ECMP)

        for idx in range(self.t2_neigh_num):
            # RIFs
            rif = sai_thrift_create_router_interface(
                self.client,
                virtual_router_id=self.default_vrf,
                src_mac_address=ROUTER_MAC,
                type=SAI_ROUTER_INTERFACE_TYPE_PORT,
                port_id=getattr(self, "port%d" % idx),
                mtu=9100)
            self.t1_config["t2"]["rifs"][idx] = rif

            for neigh in [self.t2_ipv4_neigh[idx], self.t2_ipv6_neigh[idx]]:
                # Neighbor
                nbr = sai_thrift_neighbor_entry_t(
                    rif_id=rif, ip_address=sai_ipaddress(neigh))
                sai_thrift_create_neighbor_entry(
                    self.client,
                    nbr,
                    dst_mac_address=self.t2_neigh_mac[idx])

                # NextHop
                nh_id = sai_thrift_create_next_hop(
                    self.client,
                    type=SAI_NEXT_HOP_TYPE_IP,
                    ip=sai_ipaddress(neigh),
                    router_interface_id=rif)
                self.t1_config["t2"]["nhs"][neigh] = nh_id

                # NextHop Group member
                nhg_idx = 0 if neigh in self.t2_ipv4_neigh else 1
                nhg_mbr = sai_thrift_create_next_hop_group_member(
                    self.client,
                    next_hop_group_id=self.t1_config["t2"]["nhgs"][nhg_idx],
                    next_hop_id=nh_id)
                self.t1_config["t2"]["nhg_mbrs"][neigh] = nhg_mbr

        # Default routes
        for idx, route in enumerate(["0.0.0.0/0", "::/0"]):
            t2_route = sai_thrift_route_entry_t(
                vr_id=self.default_vrf,
                destination=sai_ipprefix(route))
            nh_id = self.t1_config["t2"]["nhgs"][idx]
            sai_thrift_create_route_entry(self.client,
                                          t2_route,
                                          next_hop_id=nh_id)

        rif_first = self.t2_neigh_num
        rif_last = self.t0_neigh_num + self.t2_neigh_num
        for idx in range(rif_first, rif_last):
            # T0 RIFs
            rif = sai_thrift_create_router_interface(
                self.client,
                virtual_router_id=self.default_vrf,
                src_mac_address=ROUTER_MAC,
                type=SAI_ROUTER_INTERFACE_TYPE_PORT,
                port_id=getattr(self, "port%d" % idx),
                mtu=9100)
            self.t1_config["t0"]["rifs"][idx] = rif

    def tearDown(self):
        # T0 RIFs
        for rif in self.t1_config["t0"]["rifs"].values():
            sai_thrift_remove_router_interface(self.client, rif)
        # Default routes
        for route in ["0.0.0.0/0", "::/0"]:
            t2_route = sai_thrift_route_entry_t(
                vr_id=self.default_vrf,
                destination=sai_ipprefix(route))
            sai_thrift_remove_route_entry(self.client, t2_route)

        # For each T2 neighbor
        for idx in range(self.t2_neigh_num):
            rif = self.t1_config["t2"]["rifs"][idx]
            for neigh in [self.t2_ipv4_neigh[idx], self.t2_ipv6_neigh[idx]]:
                # NHG members
                nhg_mbr = self.t1_config["t2"]["nhg_mbrs"][neigh]
                sai_thrift_remove_next_hop_group_member(self.client, nhg_mbr)
                # NHs
                nh = self.t1_config["t2"]["nhs"][neigh]
                sai_thrift_remove_next_hop(self.client, nh)
                # Neighbors
                nbr = sai_thrift_neighbor_entry_t(
                    rif_id=rif, ip_address=sai_ipaddress(neigh))
                sai_thrift_remove_neighbor_entry(self.client, nbr)
            # RIFs
            sai_thrift_remove_router_interface(self.client, rif)

        # NHGs
        for idx in [0, 1]:
            sai_thrift_remove_next_hop_group(
                self.client,
                self.t1_config["t2"]["nhgs"][idx])
        sai_thrift_remove_router_interface(self.client, self.rif_lpb)

        super(SonicTopologyT1, self).tearDown()
