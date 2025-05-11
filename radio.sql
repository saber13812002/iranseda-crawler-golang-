/*
 Navicat Premium Dump SQL

 Source Server         : local
 Source Server Type    : MySQL
 Source Server Version : 100432 (10.4.32-MariaDB)
 Source Host           : localhost:3306
 Source Schema         : radio

 Target Server Type    : MySQL
 Target Server Version : 100432 (10.4.32-MariaDB)
 File Encoding         : 65001

 Date: 11/05/2025 20:32:30
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for downloaded_files
-- ----------------------------
DROP TABLE IF EXISTS `downloaded_files`;
CREATE TABLE `downloaded_files`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `link` text CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `downloaded_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 785 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of downloaded_files
-- ----------------------------

-- ----------------------------
-- Table structure for radio_program_sessions
-- ----------------------------
DROP TABLE IF EXISTS `radio_program_sessions`;
CREATE TABLE `radio_program_sessions`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `program_id` int NOT NULL,
  `link` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `filename` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `is_downloaded` tinyint(1) NULL DEFAULT 0,
  PRIMARY KEY (`id`) USING BTREE,
  INDEX `program_id`(`program_id` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 396 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of radio_program_sessions
-- ----------------------------
INSERT INTO `radio_program_sessions` VALUES (3, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152507883', '2024-11-08 19:39:19', 'radio-maaref-03-08-17-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (4, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152507396', '2024-11-08 19:39:19', 'radio-maaref-03-08-16-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (5, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152507432', '2024-11-08 19:39:19', 'radio-maaref-03-08-16-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (6, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152500588', '2024-11-08 19:39:19', 'radio-maaref-03-08-15-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (7, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152500629', '2024-11-08 19:39:19', 'radio-maaref-03-08-15-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (8, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152498077', '2024-11-08 19:39:19', 'radio-maaref-03-08-14-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (9, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152498117', '2024-11-08 19:39:19', 'radio-maaref-03-08-14-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (10, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497415', '2024-11-08 19:39:19', 'radio-maaref-03-08-13-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (11, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152496802', '2024-11-08 19:39:19', 'radio-maaref-03-08-13-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (12, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152496825', '2024-11-08 19:39:19', 'radio-maaref-03-08-12-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (13, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152496865', '2024-11-08 19:39:19', 'radio-maaref-03-08-12-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (14, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497006', '2024-11-08 19:39:19', 'radio-maaref-03-08-09-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (15, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497044', '2024-11-08 19:39:19', 'radio-maaref-03-08-09-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (16, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493662', '2024-11-08 19:39:19', 'radio-maaref-03-08-08-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (17, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493702', '2024-11-08 19:39:19', 'radio-maaref-03-08-08-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (18, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493725', '2024-11-08 19:39:19', 'radio-maaref-03-08-07-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (19, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493764', '2024-11-08 19:39:19', 'radio-maaref-03-08-07-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (20, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493787', '2024-11-08 19:39:19', 'radio-maaref-03-08-06-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (21, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493829', '2024-11-08 19:39:19', 'radio-maaref-03-08-06-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (22, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493853', '2024-11-08 19:39:19', 'radio-maaref-03-08-05-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (23, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548576', '2024-11-28 21:29:04', 'radio-maaref-03-09-07-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (24, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548615', '2024-11-28 21:29:04', 'radio-maaref-03-09-07-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (25, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548636', '2024-11-28 21:29:04', 'radio-maaref-03-09-06-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (26, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548677', '2024-11-28 21:29:04', 'radio-maaref-03-09-06-06-00.mp4', 1);
INSERT INTO `radio_program_sessions` VALUES (27, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152548698', '2024-11-28 21:29:04', 'radio-maaref-03-09-05-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (28, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546138', '2024-11-28 21:29:04', 'radio-maaref-03-09-05-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (29, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546159', '2024-11-28 21:29:04', 'radio-maaref-03-09-04-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (30, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546202', '2024-11-28 21:29:04', 'radio-maaref-03-09-04-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (31, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152539002', '2024-11-28 21:29:05', 'radio-maaref-03-09-03-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (32, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152539043', '2024-11-28 21:29:05', 'radio-maaref-03-09-03-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (33, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532887', '2024-11-28 21:29:05', 'radio-maaref-03-08-30-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (34, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532926', '2024-11-28 21:29:05', 'radio-maaref-03-08-30-06-00.mp4', 1);
INSERT INTO `radio_program_sessions` VALUES (35, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532949', '2024-11-28 21:29:05', 'radio-maaref-03-08-29-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (36, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152532990', '2024-11-28 21:29:05', 'radio-maaref-03-08-29-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (37, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152533013', '2024-11-28 21:29:05', 'radio-maaref-03-08-28-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (38, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152531269', '2024-11-28 21:29:05', 'radio-maaref-03-08-28-06-00.mp4', 1);
INSERT INTO `radio_program_sessions` VALUES (39, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152529456', '2024-11-28 21:29:05', 'radio-maaref-03-08-27-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (40, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152529499', '2024-11-28 21:29:05', 'radio-maaref-03-08-27-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (41, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152527024', '2024-11-28 21:29:05', 'radio-maaref-03-08-26-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (42, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152525940', '2024-11-28 21:29:05', 'radio-maaref-03-08-26-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (43, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152563040', '2024-12-05 07:05:52', 'radio-maaref-03-09-14-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (44, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152562559', '2024-12-05 07:05:52', 'radio-maaref-03-09-13-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (45, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152562596', '2024-12-05 07:05:52', 'radio-maaref-03-09-13-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (46, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559059', '2024-12-05 07:05:52', 'radio-maaref-03-09-12-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (47, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559099', '2024-12-05 07:05:52', 'radio-maaref-03-09-12-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (48, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559120', '2024-12-05 07:05:52', 'radio-maaref-03-09-11-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (49, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559163', '2024-12-05 07:05:52', 'radio-maaref-03-09-11-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (50, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559185', '2024-12-05 07:05:52', 'radio-maaref-03-09-10-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (51, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559226', '2024-12-05 07:05:52', 'radio-maaref-03-09-10-06-00.mp4', 1);
INSERT INTO `radio_program_sessions` VALUES (52, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831966', '2025-05-02 05:42:16', 'radio-maaref-04-02-10-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (53, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152832000', '2025-05-02 05:42:16', 'radio-maaref-04-02-10-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (54, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830843', '2025-05-02 05:42:16', 'radio-maaref-04-02-09-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (55, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830871', '2025-05-02 05:42:16', 'radio-maaref-04-02-09-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (56, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830926', '2025-05-02 05:42:16', 'radio-maaref-04-02-08-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (57, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827933', '2025-05-02 05:42:16', 'radio-maaref-04-02-07-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (58, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827974', '2025-05-02 05:42:16', 'radio-maaref-04-02-07-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (59, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827077', '2025-05-02 05:42:16', 'radio-maaref-04-02-06-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (60, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827116', '2025-05-02 05:42:16', 'radio-maaref-04-02-06-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (61, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823276', '2025-05-02 05:42:16', 'radio-maaref-04-02-04-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (62, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821929', '2025-05-02 05:42:16', 'radio-maaref-04-02-03-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (63, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820317', '2025-05-02 05:42:16', 'radio-maaref-04-02-02-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (64, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820358', '2025-05-02 05:42:16', 'radio-maaref-04-02-02-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (65, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152818097', '2025-05-02 05:42:16', 'radio-maaref-04-02-01-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (66, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152818139', '2025-05-02 05:42:16', 'radio-maaref-04-02-01-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (67, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152815183', '2025-05-02 05:42:16', 'radio-maaref-04-01-31-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (68, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152815224', '2025-05-02 05:42:16', 'radio-maaref-04-01-31-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (69, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152814880', '2025-05-02 05:42:16', 'radio-maaref-04-01-30-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (70, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152814919', '2025-05-02 05:42:17', 'radio-maaref-04-01-30-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (71, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809801', '2025-05-02 05:42:17', 'radio-maaref-04-01-27-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (72, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831977', '2025-05-02 05:55:16', 'radio-maaref-04-02-10-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (73, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831994', '2025-05-02 05:55:16', 'radio-maaref-04-02-10-09-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (74, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152832012', '2025-05-02 05:55:16', 'radio-maaref-04-02-10-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (75, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830883', '2025-05-02 05:55:16', 'radio-maaref-04-02-09-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (76, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821904', '2025-05-02 05:55:16', 'radio-maaref-04-02-03-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (77, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821923', '2025-05-02 05:55:16', 'radio-maaref-04-02-03-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (78, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821940', '2025-05-02 05:55:16', 'radio-maaref-04-02-03-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (79, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820333', '2025-05-02 05:55:16', 'radio-maaref-04-02-02-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (80, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820352', '2025-05-02 05:55:16', 'radio-maaref-04-02-02-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (81, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820369', '2025-05-02 05:55:16', 'radio-maaref-04-02-02-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (82, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809818', '2025-05-02 05:55:16', 'radio-maaref-04-01-27-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (83, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809837', '2025-05-02 05:55:16', 'radio-maaref-04-01-27-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (84, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809853', '2025-05-02 05:55:16', 'radio-maaref-04-01-27-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (85, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809081', '2025-05-02 05:55:16', 'radio-maaref-04-01-26-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (86, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809100', '2025-05-02 05:55:16', 'radio-maaref-04-01-26-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (87, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809116', '2025-05-02 05:55:16', 'radio-maaref-04-01-26-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (88, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802657', '2025-05-02 05:55:16', 'radio-maaref-04-01-20-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (89, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802676', '2025-05-02 05:55:16', 'radio-maaref-04-01-20-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (90, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802692', '2025-05-02 05:55:16', 'radio-maaref-04-01-20-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (91, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802720', '2025-05-02 05:55:16', 'radio-maaref-04-01-19-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (92, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834347', '2025-05-02 05:55:53', 'radio-maaref-04-02-11-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (93, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834371', '2025-05-02 05:55:53', 'radio-maaref-04-02-11-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (94, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831974', '2025-05-02 05:55:53', 'radio-maaref-04-02-10-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (95, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831998', '2025-05-02 05:55:53', 'radio-maaref-04-02-10-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (96, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830851', '2025-05-02 05:55:53', 'radio-maaref-04-02-09-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (97, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830869', '2025-05-02 05:55:53', 'radio-maaref-04-02-09-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (98, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830900', '2025-05-02 05:55:53', 'radio-maaref-04-02-08-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (99, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830924', '2025-05-02 05:55:53', 'radio-maaref-04-02-08-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (100, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827946', '2025-05-02 05:55:53', 'radio-maaref-04-02-07-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (101, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827972', '2025-05-02 05:55:53', 'radio-maaref-04-02-07-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (102, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827090', '2025-05-02 05:55:53', 'radio-maaref-04-02-06-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (103, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827114', '2025-05-02 05:55:53', 'radio-maaref-04-02-06-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (104, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824259', '2025-05-02 05:55:53', 'radio-maaref-04-02-05-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (105, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824282', '2025-05-02 05:55:53', 'radio-maaref-04-02-05-08-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (106, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823288', '2025-05-02 05:55:53', 'radio-maaref-04-02-04-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (107, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823313', '2025-05-02 05:55:53', 'radio-maaref-04-02-04-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (108, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821901', '2025-05-02 05:55:53', 'radio-maaref-04-02-03-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (109, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821927', '2025-05-02 05:55:53', 'radio-maaref-04-02-03-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (110, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820330', '2025-05-02 05:55:53', 'radio-maaref-04-02-02-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (111, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820356', '2025-05-02 05:55:53', 'radio-maaref-04-02-02-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (112, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152762333', '2025-05-02 05:57:49', 'radio-maaref-03-12-26-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (113, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152752116', '2025-05-02 05:57:49', 'radio-maaref-03-12-19-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (114, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748269', '2025-05-02 05:57:49', 'radio-maaref-03-12-12-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (115, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152731887', '2025-05-02 05:57:49', 'radio-maaref-03-11-07-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (116, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152657793', '2025-05-02 05:57:49', 'radio-maaref-03-10-30-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (117, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152655728', '2025-05-02 05:57:49', 'radio-maaref-03-10-23-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (118, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152634152', '2025-05-02 05:57:49', 'radio-maaref-03-10-16-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (119, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152628100', '2025-05-02 05:57:49', 'radio-maaref-03-10-09-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (120, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152599467', '2025-05-02 05:57:49', 'radio-maaref-03-10-02-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (121, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152584691', '2025-05-02 05:57:49', 'radio-maaref-03-09-25-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (122, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152569275', '2025-05-02 05:57:49', 'radio-maaref-03-09-18-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (123, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559116', '2025-05-02 05:57:49', 'radio-maaref-03-09-11-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (124, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152546155', '2025-05-02 05:57:49', 'radio-maaref-03-09-04-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (125, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152529452', '2025-05-02 05:57:49', 'radio-maaref-03-08-27-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (126, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152518472', '2025-05-02 05:57:49', 'radio-maaref-03-08-20-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (127, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152497411', '2025-05-02 05:57:49', 'radio-maaref-03-08-13-23-30.mp4', 1);
INSERT INTO `radio_program_sessions` VALUES (128, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152493783', '2025-05-02 05:57:49', 'radio-maaref-03-08-06-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (129, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152470142', '2025-05-02 05:57:49', 'radio-maaref-03-07-29-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (130, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152459363', '2025-05-02 05:57:49', 'radio-maaref-03-07-22-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (131, 4, '../epgarchivePart/?VALID=TRUE&ch=14&e=152452892', '2025-05-02 05:57:49', 'radio-maaref-03-07-15-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (132, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837301', '2025-05-03 21:58:01', 'radio-maaref-04-02-13-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (133, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837335', '2025-05-03 21:58:01', 'radio-maaref-04-02-13-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (134, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837309', '2025-05-03 21:58:12', 'radio-maaref-04-02-13-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (135, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837333', '2025-05-03 21:58:12', 'radio-maaref-04-02-13-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (136, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837362', '2025-05-03 21:58:12', 'radio-maaref-04-02-12-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (137, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837383', '2025-05-03 21:58:12', 'radio-maaref-04-02-12-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (138, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834350', '2025-05-03 22:07:36', 'radio-maaref-04-02-11-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (139, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834367', '2025-05-03 22:07:36', 'radio-maaref-04-02-11-09-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (140, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834384', '2025-05-03 22:07:36', 'radio-maaref-04-02-11-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (141, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824262', '2025-05-03 22:07:36', 'radio-maaref-04-02-05-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (142, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824300', '2025-05-03 22:07:36', 'radio-maaref-04-02-05-00-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (143, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823291', '2025-05-03 22:07:36', 'radio-maaref-04-02-04-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (144, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823326', '2025-05-03 22:07:36', 'radio-maaref-04-02-04-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (145, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813437', '2025-05-03 22:07:36', 'radio-maaref-04-01-29-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (146, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813475', '2025-05-03 22:07:36', 'radio-maaref-04-01-29-00-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (147, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813499', '2025-05-03 22:07:36', 'radio-maaref-04-01-28-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (148, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813518', '2025-05-03 22:07:36', 'radio-maaref-04-01-28-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (149, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813534', '2025-05-03 22:07:36', 'radio-maaref-04-01-28-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (150, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802534', '2025-05-03 22:07:36', 'radio-maaref-04-01-22-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (151, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802572', '2025-05-03 22:07:36', 'radio-maaref-04-01-22-00-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (152, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802595', '2025-05-03 22:07:36', 'radio-maaref-04-01-21-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (153, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802614', '2025-05-03 22:07:36', 'radio-maaref-04-01-21-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (154, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802630', '2025-05-03 22:07:36', 'radio-maaref-04-01-21-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (155, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152789242', '2025-05-03 22:07:36', 'radio-maaref-04-01-15-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (156, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152789280', '2025-05-03 22:07:36', 'radio-maaref-04-01-15-00-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (157, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152788093', '2025-05-03 22:07:36', 'radio-maaref-04-01-14-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (158, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837366', '2025-05-03 22:07:50', 'radio-maaref-04-02-12-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (159, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837397', '2025-05-03 22:07:50', 'radio-maaref-04-02-12-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (160, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824248', '2025-05-03 22:07:50', 'radio-maaref-04-02-05-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (161, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813423', '2025-05-03 22:07:50', 'radio-maaref-04-01-29-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (162, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802520', '2025-05-03 22:07:50', 'radio-maaref-04-01-22-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (163, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152789228', '2025-05-03 22:07:50', 'radio-maaref-04-01-15-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (164, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152781251', '2025-05-03 22:07:50', 'radio-maaref-04-01-08-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (165, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152781263', '2025-05-03 22:07:50', 'radio-maaref-04-01-08-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (166, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152769554', '2025-05-03 22:07:50', 'radio-maaref-04-01-01-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (167, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152758234', '2025-05-03 22:07:50', 'radio-maaref-03-12-24-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (168, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748040', '2025-05-03 22:07:50', 'radio-maaref-03-12-17-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (169, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748389', '2025-05-03 22:07:50', 'radio-maaref-03-12-10-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (170, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152730490', '2025-05-03 22:07:50', 'radio-maaref-03-12-03-16-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (171, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152730896', '2025-05-03 22:07:50', 'radio-maaref-03-11-26-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (172, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152731258', '2025-05-03 22:07:50', 'radio-maaref-03-11-19-16-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (173, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152731601', '2025-05-03 22:07:50', 'radio-maaref-03-11-12-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (174, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152731616', '2025-05-03 22:07:50', 'radio-maaref-03-11-12-16-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (175, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152732005', '2025-05-03 22:07:50', 'radio-maaref-03-11-05-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (176, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152732020', '2025-05-03 22:07:50', 'radio-maaref-03-11-05-16-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (177, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152655446', '2025-05-03 22:07:50', 'radio-maaref-03-10-28-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (178, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837312', '2025-05-03 22:11:51', '', 0);
INSERT INTO `radio_program_sessions` VALUES (179, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837347', '2025-05-03 22:11:51', 'radio-maaref-04-02-13-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (180, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827949', '2025-05-03 22:11:51', 'radio-maaref-04-02-07-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (181, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827093', '2025-05-03 22:11:51', 'radio-maaref-04-02-06-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (182, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152825246', '2025-05-03 22:11:51', 'radio-maaref-04-02-06-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (183, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152814896', '2025-05-03 22:11:51', 'radio-maaref-04-01-30-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (184, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152814931', '2025-05-03 22:11:51', 'radio-maaref-04-01-30-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (185, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802459', '2025-05-03 22:11:51', 'radio-maaref-04-01-23-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (186, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802480', '2025-05-03 22:11:51', 'radio-maaref-04-01-23-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (187, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802515', '2025-05-03 22:11:51', 'radio-maaref-04-01-23-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (188, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802885', '2025-05-03 22:11:51', 'radio-maaref-04-01-16-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (189, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152802906', '2025-05-03 22:11:51', 'radio-maaref-04-01-16-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (190, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152790493', '2025-05-03 22:11:51', 'radio-maaref-04-01-16-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (191, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152784395', '2025-05-03 22:11:51', 'radio-maaref-04-01-10-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (192, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152784444', '2025-05-03 22:11:51', 'radio-maaref-04-01-09-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (193, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152784456', '2025-05-03 22:11:51', 'radio-maaref-04-01-09-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (194, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152775346', '2025-05-03 22:11:51', 'radio-maaref-04-01-04-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (195, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152773987', '2025-05-03 22:11:51', 'radio-maaref-04-01-03-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (196, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152772317', '2025-05-03 22:11:51', 'radio-maaref-04-01-02-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (197, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152759741', '2025-05-03 22:11:51', 'radio-maaref-03-12-25-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (198, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152781267', '2025-05-03 22:14:49', 'radio-maaref-04-01-08-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (199, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152769558', '2025-05-03 22:14:49', 'radio-maaref-04-01-01-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (200, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152758238', '2025-05-03 22:14:49', 'radio-maaref-03-12-24-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (201, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748044', '2025-05-03 22:14:49', 'radio-maaref-03-12-17-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (202, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748393', '2025-05-03 22:14:49', 'radio-maaref-03-12-10-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (203, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152730494', '2025-05-03 22:14:49', 'radio-maaref-03-12-03-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (204, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152730899', '2025-05-03 22:14:49', 'radio-maaref-03-11-26-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (205, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152731262', '2025-05-03 22:14:49', 'radio-maaref-03-11-19-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (206, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152731620', '2025-05-03 22:14:49', 'radio-maaref-03-11-12-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (207, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152732024', '2025-05-03 22:14:49', 'radio-maaref-03-11-05-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (208, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152655465', '2025-05-03 22:14:49', 'radio-maaref-03-10-28-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (209, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152655871', '2025-05-03 22:14:49', 'radio-maaref-03-10-21-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (210, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152634296', '2025-05-03 22:14:49', 'radio-maaref-03-10-14-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (211, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152606770', '2025-05-03 22:14:49', 'radio-maaref-03-10-07-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (212, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152595550', '2025-05-03 22:14:49', 'radio-maaref-03-09-30-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (213, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152578448', '2025-05-03 22:14:49', 'radio-maaref-03-09-23-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (214, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152565821', '2025-05-03 22:14:49', 'radio-maaref-03-09-16-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (215, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152559264', '2025-05-03 22:14:49', 'radio-maaref-03-09-09-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (216, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152535796', '2025-05-03 22:14:49', 'radio-maaref-03-09-02-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (217, 8, '../epgarchivePart/?VALID=TRUE&ch=14&e=152525498', '2025-05-03 22:14:49', 'radio-maaref-03-08-25-14-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (218, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837317', '2025-05-03 22:15:54', 'radio-maaref-04-02-13-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (219, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152837370', '2025-05-03 22:15:54', 'radio-maaref-04-02-12-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (220, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152834355', '2025-05-03 22:15:54', 'radio-maaref-04-02-11-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (221, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152831982', '2025-05-03 22:15:54', 'radio-maaref-04-02-10-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (222, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830856', '2025-05-03 22:15:54', 'radio-maaref-04-02-09-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (223, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152830908', '2025-05-03 22:15:54', 'radio-maaref-04-02-08-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (224, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827954', '2025-05-03 22:15:54', 'radio-maaref-04-02-07-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (225, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152827098', '2025-05-03 22:15:54', 'radio-maaref-04-02-06-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (226, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152824267', '2025-05-03 22:15:54', 'radio-maaref-04-02-05-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (227, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152823297', '2025-05-03 22:15:54', 'radio-maaref-04-02-04-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (228, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152821909', '2025-05-03 22:15:54', '', 0);
INSERT INTO `radio_program_sessions` VALUES (229, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152820338', '2025-05-03 22:15:54', 'radio-maaref-04-02-02-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (230, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152818119', '2025-05-03 22:15:54', 'radio-maaref-04-02-01-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (231, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152815204', '2025-05-03 22:15:54', 'radio-maaref-04-01-31-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (232, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152814901', '2025-05-03 22:15:54', 'radio-maaref-04-01-30-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (233, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813442', '2025-05-03 22:15:54', 'radio-maaref-04-01-29-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (234, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152813504', '2025-05-03 22:15:54', 'radio-maaref-04-01-28-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (235, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809823', '2025-05-03 22:15:54', 'radio-maaref-04-01-27-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (236, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152809086', '2025-05-03 22:15:54', 'radio-maaref-04-01-26-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (237, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152807184', '2025-05-03 22:15:54', 'radio-maaref-04-01-25-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (238, 10, '../epgarchivePart/?VALID=TRUE&ch=14&e=146649527', '2025-05-03 22:16:48', 'radio-maaref-98-12-18-10-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (239, 10, '../epgarchivePart/?VALID=TRUE&ch=14&e=145189232', '2025-05-03 22:16:49', 'radio-maaref-97-12-28-20-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (240, 10, '../epgarchivePart/?VALID=TRUE&ch=14&e=139510046', '2025-05-03 22:16:49', 'radio-maaref-97-01-10-22-30.mp4', 1);
INSERT INTO `radio_program_sessions` VALUES (241, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152784403', '2025-05-06 09:13:18', 'radio-maaref-04-01-10-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (242, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152784454', '2025-05-06 09:13:18', 'radio-maaref-04-01-09-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (243, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152780397', '2025-05-06 09:13:18', 'radio-maaref-04-01-07-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (244, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152779498', '2025-05-06 09:13:18', 'radio-maaref-04-01-06-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (245, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152776919', '2025-05-06 09:13:18', 'radio-maaref-04-01-05-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (246, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152775344', '2025-05-06 09:13:18', 'radio-maaref-04-01-04-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (247, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152773985', '2025-05-06 09:13:18', 'radio-maaref-04-01-03-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (248, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152772315', '2025-05-06 09:13:18', 'radio-maaref-04-01-02-17-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (249, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152767716', '2025-05-06 09:13:18', 'radio-maaref-03-12-29-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (250, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152766030', '2025-05-06 09:13:18', 'radio-maaref-03-12-28-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (251, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152763413', '2025-05-06 09:13:18', 'radio-maaref-03-12-27-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (252, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152762343', '2025-05-06 09:13:18', 'radio-maaref-03-12-26-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (253, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152759771', '2025-05-06 09:13:18', 'radio-maaref-03-12-25-02-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (254, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152753256', '2025-05-06 09:13:18', 'radio-maaref-03-12-21-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (255, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152752126', '2025-05-06 09:13:18', 'radio-maaref-03-12-19-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (256, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748796', '2025-05-06 09:13:18', 'radio-maaref-03-12-18-02-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (257, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152748369', '2025-05-06 09:13:18', 'radio-maaref-03-12-11-02-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (258, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152730408', '2025-05-06 09:13:18', 'radio-maaref-03-12-05-02-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (259, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152730466', '2025-05-06 09:13:18', 'radio-maaref-03-12-04-02-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (260, 11, '../epgarchivePart/?VALID=TRUE&ch=14&e=152730813', '2025-05-06 09:13:18', 'radio-maaref-03-11-28-02-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (261, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845217', '2025-05-07 09:05:55', 'radio-maaref-04-02-16-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (262, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845273', '2025-05-07 09:05:55', 'radio-maaref-04-02-15-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (263, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845328', '2025-05-07 09:05:55', 'radio-maaref-04-02-14-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (264, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845385', '2025-05-07 09:05:55', 'radio-maaref-04-02-13-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (265, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845436', '2025-05-07 09:05:55', 'radio-maaref-04-02-12-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (266, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845488', '2025-05-07 09:05:55', 'radio-maaref-04-02-11-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (267, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845542', '2025-05-07 09:05:55', 'radio-maaref-04-02-10-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (268, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845594', '2025-05-07 09:05:55', 'radio-maaref-04-02-09-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (269, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845646', '2025-05-07 09:05:55', 'radio-maaref-04-02-08-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (270, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845706', '2025-05-07 09:05:55', 'radio-maaref-04-02-07-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (271, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845768', '2025-05-07 09:05:55', 'radio-maaref-04-02-06-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (272, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845824', '2025-05-07 09:05:55', 'radio-maaref-04-02-05-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (273, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845884', '2025-05-07 09:05:55', 'radio-maaref-04-02-04-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (274, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845937', '2025-05-07 09:05:55', 'radio-maaref-04-02-03-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (275, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845998', '2025-05-07 09:05:55', 'radio-maaref-04-02-02-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (276, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846060', '2025-05-07 09:05:55', 'radio-maaref-04-02-01-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (277, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846121', '2025-05-07 09:05:55', 'radio-maaref-04-01-31-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (278, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846183', '2025-05-07 09:05:55', 'radio-maaref-04-01-30-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (279, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846239', '2025-05-07 09:05:55', 'radio-maaref-04-01-29-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (280, 12, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846301', '2025-05-07 09:05:55', 'radio-maaref-04-01-28-11-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (281, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152858741', '2025-05-11 20:05:50', 'radio-maaref-04-02-21-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (282, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152857289', '2025-05-11 20:05:50', 'radio-maaref-04-02-20-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (283, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152857328', '2025-05-11 20:05:50', 'radio-maaref-04-02-20-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (284, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152849816', '2025-05-11 20:05:50', 'radio-maaref-04-02-17-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (285, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845228', '2025-05-11 20:05:50', 'radio-maaref-04-02-16-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (286, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845284', '2025-05-11 20:05:50', 'radio-maaref-04-02-15-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (287, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845304', '2025-05-11 20:05:50', 'radio-maaref-04-02-14-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (288, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845339', '2025-05-11 20:05:50', 'radio-maaref-04-02-14-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (289, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845360', '2025-05-11 20:05:50', 'radio-maaref-04-02-13-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (290, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845394', '2025-05-11 20:05:50', 'radio-maaref-04-02-13-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (291, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845517', '2025-05-11 20:05:50', 'radio-maaref-04-02-10-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (292, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845551', '2025-05-11 20:05:50', 'radio-maaref-04-02-10-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (293, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845572', '2025-05-11 20:05:50', 'radio-maaref-04-02-09-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (294, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845600', '2025-05-11 20:05:50', 'radio-maaref-04-02-09-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (295, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845655', '2025-05-11 20:05:50', 'radio-maaref-04-02-08-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (296, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845676', '2025-05-11 20:05:50', 'radio-maaref-04-02-07-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (297, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845717', '2025-05-11 20:05:50', 'radio-maaref-04-02-07-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (298, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845738', '2025-05-11 20:05:50', 'radio-maaref-04-02-06-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (299, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845777', '2025-05-11 20:05:50', 'radio-maaref-04-02-06-06-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (300, 1, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845854', '2025-05-11 20:05:50', 'radio-maaref-04-02-04-21-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (301, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152858714', '2025-05-11 20:05:50', 'radio-maaref-04-02-21-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (302, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152858739', '2025-05-11 20:05:50', 'radio-maaref-04-02-21-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (303, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152857302', '2025-05-11 20:05:50', 'radio-maaref-04-02-20-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (304, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152857326', '2025-05-11 20:05:50', 'radio-maaref-04-02-20-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (305, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152853883', '2025-05-11 20:05:50', 'radio-maaref-04-02-19-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (306, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152853902', '2025-05-11 20:05:50', 'radio-maaref-04-02-19-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (307, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852415', '2025-05-11 20:05:50', 'radio-maaref-04-02-18-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (308, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852440', '2025-05-11 20:05:50', 'radio-maaref-04-02-18-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (309, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852473', '2025-05-11 20:05:50', 'radio-maaref-04-02-17-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (310, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152849814', '2025-05-11 20:05:50', 'radio-maaref-04-02-17-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (311, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845201', '2025-05-11 20:05:50', 'radio-maaref-04-02-16-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (312, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845226', '2025-05-11 20:05:50', 'radio-maaref-04-02-16-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (313, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845258', '2025-05-11 20:05:50', 'radio-maaref-04-02-15-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (314, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845282', '2025-05-11 20:05:50', 'radio-maaref-04-02-15-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (315, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845312', '2025-05-11 20:05:50', 'radio-maaref-04-02-14-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (316, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845337', '2025-05-11 20:05:50', 'radio-maaref-04-02-14-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (317, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845368', '2025-05-11 20:05:50', 'radio-maaref-04-02-13-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (318, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845392', '2025-05-11 20:05:50', 'radio-maaref-04-02-13-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (319, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845421', '2025-05-11 20:05:50', 'radio-maaref-04-02-12-18-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (320, 2, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845442', '2025-05-11 20:05:50', 'radio-maaref-04-02-12-07-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (321, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852476', '2025-05-11 20:05:51', 'radio-maaref-04-02-17-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (322, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152849827', '2025-05-11 20:05:51', 'radio-maaref-04-02-17-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (323, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845204', '2025-05-11 20:05:51', 'radio-maaref-04-02-16-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (324, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845222', '2025-05-11 20:05:51', 'radio-maaref-04-02-16-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (325, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845239', '2025-05-11 20:05:51', 'radio-maaref-04-02-16-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (326, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845528', '2025-05-11 20:05:51', 'radio-maaref-04-02-10-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (327, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845545', '2025-05-11 20:05:51', 'radio-maaref-04-02-10-09-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (328, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845563', '2025-05-11 20:05:51', 'radio-maaref-04-02-10-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (329, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845612', '2025-05-11 20:05:51', 'radio-maaref-04-02-09-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (330, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845923', '2025-05-11 20:05:51', 'radio-maaref-04-02-03-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (331, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845942', '2025-05-11 20:05:51', 'radio-maaref-04-02-03-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (332, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845959', '2025-05-11 20:05:51', 'radio-maaref-04-02-03-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (333, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845984', '2025-05-11 20:05:51', 'radio-maaref-04-02-02-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (334, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846003', '2025-05-11 20:05:51', 'radio-maaref-04-02-02-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (335, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846020', '2025-05-11 20:05:51', 'radio-maaref-04-02-02-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (336, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846349', '2025-05-11 20:05:51', 'radio-maaref-04-01-27-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (337, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846368', '2025-05-11 20:05:51', 'radio-maaref-04-01-27-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (338, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846384', '2025-05-11 20:05:51', 'radio-maaref-04-01-27-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (339, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846410', '2025-05-11 20:05:51', 'radio-maaref-04-01-26-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (340, 3, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846429', '2025-05-11 20:05:51', 'radio-maaref-04-01-26-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (341, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852418', '2025-05-11 20:05:52', 'radio-maaref-04-02-18-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (342, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852436', '2025-05-11 20:05:52', 'radio-maaref-04-02-18-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (343, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852453', '2025-05-11 20:05:52', 'radio-maaref-04-02-18-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (344, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845474', '2025-05-11 20:05:52', 'radio-maaref-04-02-11-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (345, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845491', '2025-05-11 20:05:52', 'radio-maaref-04-02-11-09-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (346, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845508', '2025-05-11 20:05:52', 'radio-maaref-04-02-11-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (347, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845847', '2025-05-11 20:05:52', 'radio-maaref-04-02-05-00-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (348, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845869', '2025-05-11 20:05:52', 'radio-maaref-04-02-04-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (349, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845904', '2025-05-11 20:05:52', 'radio-maaref-04-02-04-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (350, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846263', '2025-05-11 20:05:52', 'radio-maaref-04-01-29-00-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (351, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846287', '2025-05-11 20:05:52', 'radio-maaref-04-01-28-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (352, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846306', '2025-05-11 20:05:52', 'radio-maaref-04-01-28-09-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (353, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846322', '2025-05-11 20:05:52', 'radio-maaref-04-01-28-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (354, 5, '../epgarchivePart/?VALID=TRUE&ch=14&e=152788110', '2025-05-11 20:05:52', 'radio-maaref-04-01-14-09-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (355, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152853887', '2025-05-11 20:05:53', 'radio-maaref-04-02-19-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (356, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152853916', '2025-05-11 20:05:53', 'radio-maaref-04-02-19-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (357, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845425', '2025-05-11 20:05:53', 'radio-maaref-04-02-12-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (358, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845456', '2025-05-11 20:05:53', 'radio-maaref-04-02-12-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (359, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845812', '2025-05-11 20:05:53', 'radio-maaref-04-02-05-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (360, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845845', '2025-05-11 20:05:53', 'radio-maaref-04-02-05-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (361, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846208', '2025-05-11 20:05:53', 'radio-maaref-04-01-29-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (362, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846225', '2025-05-11 20:05:53', 'radio-maaref-04-01-29-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (363, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846655', '2025-05-11 20:05:53', 'radio-maaref-04-01-22-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (364, 6, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846688', '2025-05-11 20:05:53', 'radio-maaref-04-01-22-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (365, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152857305', '2025-05-11 20:05:55', 'radio-maaref-04-02-20-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (366, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845371', '2025-05-11 20:05:55', 'radio-maaref-04-02-13-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (367, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845406', '2025-05-11 20:05:55', 'radio-maaref-04-02-13-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (368, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845692', '2025-05-11 20:05:55', 'radio-maaref-04-02-07-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (369, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845754', '2025-05-11 20:05:55', 'radio-maaref-04-02-06-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (370, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845789', '2025-05-11 20:05:55', 'radio-maaref-04-02-06-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (371, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846169', '2025-05-11 20:05:55', 'radio-maaref-04-01-30-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (372, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846204', '2025-05-11 20:05:55', 'radio-maaref-04-01-30-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (373, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846573', '2025-05-11 20:05:55', 'radio-maaref-04-01-23-23-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (374, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846594', '2025-05-11 20:05:55', 'radio-maaref-04-01-23-16-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (375, 7, '../epgarchivePart/?VALID=TRUE&ch=14&e=152846629', '2025-05-11 20:05:55', 'radio-maaref-04-01-23-02-00.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (376, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152858722', '2025-05-11 20:05:57', 'radio-maaref-04-02-21-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (377, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152857310', '2025-05-11 20:05:57', 'radio-maaref-04-02-20-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (378, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152853891', '2025-05-11 20:05:57', 'radio-maaref-04-02-19-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (379, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852422', '2025-05-11 20:05:57', 'radio-maaref-04-02-18-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (380, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152852480', '2025-05-11 20:05:57', 'radio-maaref-04-02-17-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (381, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845208', '2025-05-11 20:05:57', 'radio-maaref-04-02-16-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (382, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845265', '2025-05-11 20:05:57', 'radio-maaref-04-02-15-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (383, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845319', '2025-05-11 20:05:57', 'radio-maaref-04-02-14-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (384, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845376', '2025-05-11 20:05:57', 'radio-maaref-04-02-13-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (385, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845429', '2025-05-11 20:05:57', 'radio-maaref-04-02-12-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (386, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845479', '2025-05-11 20:05:57', 'radio-maaref-04-02-11-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (387, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845533', '2025-05-11 20:05:57', 'radio-maaref-04-02-10-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (388, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845585', '2025-05-11 20:05:57', 'radio-maaref-04-02-09-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (389, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845637', '2025-05-11 20:05:57', 'radio-maaref-04-02-08-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (390, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845697', '2025-05-11 20:05:57', 'radio-maaref-04-02-07-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (391, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845759', '2025-05-11 20:05:57', 'radio-maaref-04-02-06-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (392, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845817', '2025-05-11 20:05:57', 'radio-maaref-04-02-05-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (393, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845875', '2025-05-11 20:05:57', 'radio-maaref-04-02-04-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (394, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845928', '2025-05-11 20:05:57', 'radio-maaref-04-02-03-13-30.mp3', 1);
INSERT INTO `radio_program_sessions` VALUES (395, 9, '../epgarchivePart/?VALID=TRUE&ch=14&e=152845989', '2025-05-11 20:05:57', 'radio-maaref-04-02-02-13-30.mp3', 1);

-- ----------------------------
-- Table structure for radio_programs
-- ----------------------------
DROP TABLE IF EXISTS `radio_programs`;
CREATE TABLE `radio_programs`  (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `url` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL DEFAULT NULL,
  `time` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 13 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of radio_programs
-- ----------------------------
INSERT INTO `radio_programs` VALUES (1, 'بر كرانه نور\n\n					', 'https://radio.iranseda.ir/Program/?https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044116', '05', '2024-11-08 16:30:00');
INSERT INTO `radio_programs` VALUES (2, 'گنج سعادت\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=046104', '02', '2025-05-02 05:52:49');
INSERT INTO `radio_programs` VALUES (3, ' پرسمان اعتقادی\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045101', '19', '2025-05-02 05:54:06');
INSERT INTO `radio_programs` VALUES (4, 'پرسمان خانواده\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044323', '15', '2025-05-02 05:57:49');
INSERT INTO `radio_programs` VALUES (5, ' پرسمان انقلاب\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=047545', '14', '2025-05-03 22:07:36');
INSERT INTO `radio_programs` VALUES (6, '\n\n					پرسمان تاریخی', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045102', '28', '2025-05-03 22:07:50');
INSERT INTO `radio_programs` VALUES (7, 'پرسمان قرآنی\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045103', '25', '2025-05-03 22:11:51');
INSERT INTO `radio_programs` VALUES (8, 'پرسمان مهدوی\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=046111', '25', '2025-05-03 22:14:49');
INSERT INTO `radio_programs` VALUES (9, 'پیام ولایت\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=044125', '25', '2025-05-03 22:15:54');
INSERT INTO `radio_programs` VALUES (10, 'امیر مؤمنان\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=047506', '10', '2025-05-03 22:16:49');
INSERT INTO `radio_programs` VALUES (11, 'امیر جان ها\n\n					', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=045504', '28', '2025-05-06 09:13:18');
INSERT INTO `radio_programs` VALUES (12, '\n\n					اخبار معارفی', 'https://radio.iranseda.ir/Program/?VALID=TRUE&ch=14&m=048113', '28', '2025-05-07 09:05:55');

SET FOREIGN_KEY_CHECKS = 1;
