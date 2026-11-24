// SPDX-License-Identifier: GPL-2.0
/*
 * Add/delete IPv4 MFC entries to exercise the 0604-1 callback consumer.
 * Usage: ax6-mfc-test [cycles] [origin] [group]
 */
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include <linux/mroute.h>

static int do_vif(int fd, int add)
{
	struct vifctl v;

	memset(&v, 0, sizeof(v));
	v.vifc_vifi = 0;
	v.vifc_flags = 0;
	v.vifc_threshold = 1;
	v.vifc_rate_limit = 0;
	v.vifc_lcl_addr.s_addr = inet_addr("192.168.5.1");
	v.vifc_rmt_addr.s_addr = INADDR_ANY;

	if (setsockopt(fd, IPPROTO_IP, add ? MRT_ADD_VIF : MRT_DEL_VIF,
		       &v, sizeof(v)) < 0) {
		if (errno == EEXIST && add)
			return 0;
		perror("MRT_ADD/DEL_VIF");
		return -1;
	}
	return 0;
}

int main(int argc, char **argv)
{
	int cycles = argc > 1 ? atoi(argv[1]) : 20;
	const char *origin_s = argc > 2 ? argv[2] : "10.10.10.10";
	const char *group_s = argc > 3 ? argv[3] : "239.10.10.10";
	struct in_addr origin, group;
	struct mfcctl m;
	int fd, i, ret = 0;
	int one = 1;

	if (cycles <= 0)
		cycles = 1;
	if (inet_aton(origin_s, &origin) == 0 || inet_aton(group_s, &group) == 0) {
		fprintf(stderr, "bad origin/group\n");
		return 2;
	}

	fd = socket(AF_INET, SOCK_RAW, IPPROTO_ICMP);
	if (fd < 0) {
		perror("socket");
		return 2;
	}
	if (setsockopt(fd, IPPROTO_IP, MRT_INIT, &one, sizeof(one)) < 0) {
		perror("MRT_INIT");
		close(fd);
		return 2;
	}
	if (do_vif(fd, 1) < 0) {
		setsockopt(fd, IPPROTO_IP, MRT_DONE, &one, sizeof(one));
		close(fd);
		return 2;
	}

	for (i = 0; i < cycles; i++) {
		memset(&m, 0, sizeof(m));
		m.mfcc_origin = origin;
		m.mfcc_mcastgrp = group;
		m.mfcc_parent = 0;
		m.mfcc_ttls[0] = 1;
		if (setsockopt(fd, IPPROTO_IP, MRT_ADD_MFC, &m, sizeof(m)) < 0) {
			fprintf(stderr, "cycle %d MRT_ADD_MFC: %s\n", i, strerror(errno));
			ret = 1;
			break;
		}
		if (setsockopt(fd, IPPROTO_IP, MRT_DEL_MFC, &m, sizeof(m)) < 0) {
			fprintf(stderr, "cycle %d MRT_DEL_MFC: %s\n", i, strerror(errno));
			ret = 1;
			break;
		}
	}
	if (!ret)
		printf("PASS cycles=%d origin=%s group=%s\n", cycles, origin_s, group_s);

	do_vif(fd, 0);
	setsockopt(fd, IPPROTO_IP, MRT_DONE, &one, sizeof(one));
	close(fd);
	return ret;
}
