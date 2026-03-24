import numpy as np
from scipy.optimize import linear_sum_assignment
from collections import defaultdict

def calculate_iou(boxA, boxB):
    """
    Calculate the Intersection over Union (IoU) of two bounding boxes.
    Format: [x1, y1, x2, y2]
    """
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)

    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou

def evaluate_detection_frame(gt_boxes, pred_boxes, iou_threshold=0.5):
    """
    Evaluates detection precision and recall for a single frame using IoU matching.
    
    Args:
        gt_boxes: List of Ground Truth boxes [x1, y1, x2, y2].
        pred_boxes: List of Predicted boxes [x1, y1, x2, y2].
        iou_threshold: Minimum IoU to consider a True Positive.
        
    Returns:
        dict: {'tp': int, 'fp': int, 'fn': int}
    """
    if len(pred_boxes) == 0:
        return {'tp': 0, 'fp': 0, 'fn': len(gt_boxes)}
        
    if len(gt_boxes) == 0:
        return {'tp': 0, 'fp': len(pred_boxes), 'fn': 0}

    # Cost matrix for Hungarian Algorithm (1 - IoU)
    cost_matrix = np.ones((len(gt_boxes), len(pred_boxes)))
    
    for i, gt_box in enumerate(gt_boxes):
        for j, pred_box in enumerate(pred_boxes):
            iou = calculate_iou(gt_box, pred_box)
            if iou >= iou_threshold:
                cost_matrix[i, j] = 1 - iou
                
    gt_indices, pred_indices = linear_sum_assignment(cost_matrix)
    
    tp = 0
    assigned_pred = set()
    assigned_gt = set()
    
    for gt_idx, pred_idx in zip(gt_indices, pred_indices):
        if cost_matrix[gt_idx, pred_idx] < 1.0: # iou >= threshold
            tp += 1
            assigned_pred.add(pred_idx)
            assigned_gt.add(gt_idx)
            
    fp = len(pred_boxes) - len(assigned_pred)
    fn = len(gt_boxes) - len(assigned_gt)
    
    return {'tp': tp, 'fp': fp, 'fn': fn}

def evaluate_tracking_frame(gt_tracks, pred_tracks, distance_threshold=0.5):
    """
    Evaluate ID switches and matches for MOTA calculation for a single frame.
    
    Args:
        gt_tracks: Dict of {track_id: [x1, y1, x2, y2]} for GT in current frame.
        pred_tracks: Dict of {track_id: [x1, y1, x2, y2]} for predictions.
    
    Returns:
        matches: List of tuples (gt_id, pred_id)
        fps: List of predicted track_ids that didn't match
        mismatches: List of ground truth track_ids that didn't match (misses)
    """
    gt_ids = list(gt_tracks.keys())
    pred_ids = list(pred_tracks.keys())
    
    if not gt_ids and not pred_ids:
        return [], [], []
    if not gt_ids:
        return [], pred_ids, []
    if not pred_ids:
        return [], [], gt_ids
        
    cost_matrix = np.ones((len(gt_ids), len(pred_ids)))
    
    for i, g_id in enumerate(gt_ids):
        for j, p_id in enumerate(pred_ids):
            iou = calculate_iou(gt_tracks[g_id], pred_tracks[p_id])
            if iou >= distance_threshold:
                cost_matrix[i, j] = 1 - iou
                
    g_idx, p_idx = linear_sum_assignment(cost_matrix)
    
    matches = []
    matched_gt = set()
    matched_pred = set()
    
    for g, p in zip(g_idx, p_idx):
        if cost_matrix[g, p] < 1.0:
            matches.append((gt_ids[g], pred_ids[p]))
            matched_gt.add(gt_ids[g])
            matched_pred.add(pred_ids[p])
            
    fps = [p_id for p_id in pred_ids if p_id not in matched_pred]
    misses = [g_id for g_id in gt_ids if g_id not in matched_gt]
    
    return matches, fps, misses
