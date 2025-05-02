/*
 Navicat Premium Data Transfer

 Source Server         : localhost_3306
 Source Server Type    : MySQL
 Source Server Version : 100432
 Source Host           : localhost:3306
 Source Schema         : radio

 Target Server Type    : MySQL
 Target Server Version : 100432
 File Encoding         : 65001

 Date: 02/05/2025 06:20:52
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for radio_program_sessions
-- ----------------------------
DROP TABLE IF EXISTS `radio_program_sessions`;
CREATE TABLE `radio_program_sessions`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `link` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `program_id`(`program_id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 132 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of radio_program_sessions
-- ----------------------------
INSERT INTO `radio_program_sessions` VALUES (3, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152507883', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (4, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152507396', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (5, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152507432', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (6, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152500588', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (7, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152500629', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (8, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152498077', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (9, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152498117', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (10, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497415', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (11, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152496802', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (12, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152496825', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (13, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152496865', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (14, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497006', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (15, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497044', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (16, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493662', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (17, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493702', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (18, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493725', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (19, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493764', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (20, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493787', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (21, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493829', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (22, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493853', '2024-11-08 19:39:19');
INSERT INTO `radio_program_sessions` VALUES (23, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548576', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (24, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548615', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (25, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548636', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (26, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548677', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (27, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548698', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (28, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546138', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (29, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546159', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (30, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546202', '2024-11-28 21:29:04');
INSERT INTO `radio_program_sessions` VALUES (31, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152539002', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (32, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152539043', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (33, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532887', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (34, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532926', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (35, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532949', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (36, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532990', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (37, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152533013', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (38, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152531269', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (39, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152529456', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (40, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152529499', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (41, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152527024', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (42, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152525940', '2024-11-28 21:29:05');
INSERT INTO `radio_program_sessions` VALUES (43, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152563040', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (44, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152562559', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (45, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152562596', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (46, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559059', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (47, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559099', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (48, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559120', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (49, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559163', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (50, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559185', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (51, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559226', '2024-12-05 07:05:52');
INSERT INTO `radio_program_sessions` VALUES (52, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831966', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (53, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152832000', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (54, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830843', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (55, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830871', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (56, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830926', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (57, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827933', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (58, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827974', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (59, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827077', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (60, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827116', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (61, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823276', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (62, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821929', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (63, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820317', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (64, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820358', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (65, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152818097', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (66, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152818139', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (67, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152815183', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (68, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152815224', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (69, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152814880', '2025-05-02 05:42:16');
INSERT INTO `radio_program_sessions` VALUES (70, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152814919', '2025-05-02 05:42:17');
INSERT INTO `radio_program_sessions` VALUES (71, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809801', '2025-05-02 05:42:17');
INSERT INTO `radio_program_sessions` VALUES (72, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831977', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (73, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831994', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (74, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152832012', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (75, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830883', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (76, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821904', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (77, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821923', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (78, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821940', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (79, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820333', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (80, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820352', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (81, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820369', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (82, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809818', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (83, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809837', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (84, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809853', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (85, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809081', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (86, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809100', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (87, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809116', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (88, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802657', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (89, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802676', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (90, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802692', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (91, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802720', '2025-05-02 05:55:16');
INSERT INTO `radio_program_sessions` VALUES (92, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834347', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (93, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834371', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (94, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831974', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (95, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831998', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (96, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830851', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (97, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830869', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (98, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830900', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (99, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830924', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (100, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827946', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (101, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827972', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (102, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827090', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (103, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827114', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (104, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824259', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (105, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824282', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (106, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823288', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (107, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823313', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (108, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821901', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (109, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821927', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (110, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820330', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (111, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820356', '2025-05-02 05:55:53');
INSERT INTO `radio_program_sessions` VALUES (112, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152762333', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (113, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152752116', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (114, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748269', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (115, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152731887', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (116, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152657793', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (117, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152655728', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (118, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152634152', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (119, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152628100', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (120, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152599467', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (121, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152584691', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (122, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152569275', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (123, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559116', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (124, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546155', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (125, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152529452', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (126, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152518472', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (127, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497411', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (128, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493783', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (129, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152470142', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (130, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152459363', '2025-05-02 05:57:49');
INSERT INTO `radio_program_sessions` VALUES (131, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152452892', '2025-05-02 05:57:49');

-- ----------------------------
-- Table structure for radio_programs
-- ----------------------------
DROP TABLE IF EXISTS `radio_programs`;
CREATE TABLE `radio_programs`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `time` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 5 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of radio_programs
-- ----------------------------
INSERT INTO `radio_programs` VALUES (1, 'بر كرانه نور\n\n					', '05', '2024-11-08 16:30:00');
INSERT INTO `radio_programs` VALUES (2, 'گنج سعادت\n\n					', '02', '2025-05-02 05:52:49');
INSERT INTO `radio_programs` VALUES (3, ' پرسمان اعتقادی\n\n					', '19', '2025-05-02 05:54:06');
INSERT INTO `radio_programs` VALUES (4, 'پرسمان خانواده\n\n					', '15', '2025-05-02 05:57:49');

SET FOREIGN_KEY_CHECKS = 1;
