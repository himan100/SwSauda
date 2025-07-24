// const { use } = require("react");

use('Pinaka');
// Drop the view if it already exists
db.v_index_base.drop();

// Create the view
db.createView(
  'v_index_base',
  'IndexTick',
  [
    {
      $sort: { ft: 1 }
    },
    {
      $limit: 150
    },
    {
      $match: {
        $expr: {
          $eq: [{ $mod: ['$ft', 60] }, 0]
        }
      }
    },
    {
      $group: {
        _id: null,
        minFt: { $min: '$ft' }
      }
    },
    {
      $lookup: {
        from: "IndexTick",
        let: { minFt: "$minFt" },
        pipeline: [
          {
            $match: {
              $expr: { $eq: ["$ft", "$$minFt"] }
            }
          },
          {
            $lookup: {
              from: "Index",
              localField: "token",
              foreignField: "token",
              as: "indexData"
            }
          },
          {
            $unwind: "$indexData"
          },
          {
            $replaceRoot: {
              newRoot: { $mergeObjects: [ "$$ROOT", "$indexData" ] }
            }
          },
          {
            $unset: "indexData"
          },
          {
            $addFields: {
              ibase: {
                $multiply: [
                  { $floor: { $divide: ["$lp", "$strkstep"] } },
                  "$strkstep"
                ]
              },
              itop: {
                $multiply: [
                  { $ceil: { $divide: ["$lp", "$strkstep"] } },
                  "$strkstep"
                ]
              }
            }
          }
        ],
        as: "results"
      }
    },
    {
      $unwind: "$results"
    },
    {
      $replaceRoot: { newRoot: "$results" }
    }
  ]
);

print('View created successfully.'); 

db.v_option_pair_base.drop();

db.createView(
  'v_option_pair_base',
  'IndexTick',
  [
    {
      $match: {
        $expr: {
          $eq: [{ $mod: ['$ft', 300] }, 0]
        }
      }
    },
    {
      $lookup: {
        from: "Index",
        localField: "token",
        foreignField: "token",
        as: "indexData"
      }
    },
    {
      $unwind: "$indexData"
    },
    {
      $replaceRoot: {
        newRoot: { $mergeObjects: [ "$$ROOT", "$indexData" ] }
      }
    },
    {
      $unset: "indexData"
    },
    {
      $addFields: {
        ibase: {
          $multiply: [
            { $floor: { $divide: ["$lp", "$strkstep"] } },
            "$strkstep"
          ]
        },
        itop: {
          $multiply: [
            { $ceil: { $divide: ["$lp", "$strkstep"] } },
            "$strkstep"
          ]
        }
      }
    },
    {
      $addFields: {
        levels: { $range: [0, 10, 1] }
      }
    },
    {
      $unwind: "$levels"
    },
    {
      $addFields: {
        level: "$levels",
        ce_strike: { $subtract: ["$ibase", { $multiply: ["$strkstep", "$levels"] }] },
        pe_strike: { $add: ["$itop", { $multiply: ["$strkstep", "$levels"] }] }
      }
    },
    {
      $lookup: {
        from: "Option",
        let: { strike: "$ce_strike" },
        pipeline: [
          {
            $match: {
              $expr: {
                $and: [
                  { $eq: ["$strprc", "$$strike"] },
                  { $eq: ["$optt", "CE"] }
                ]
              }
            }
          }
        ],
        as: "ceOption"
      }
    },
    {
      $lookup: {
        from: "Option",
        let: { strike: "$pe_strike" },
        pipeline: [
          {
            $match: {
              $expr: {
                $and: [
                  { $eq: ["$strprc", "$$strike"] },
                  { $eq: ["$optt", "PE"] }
                ]
              }
            }
          }
        ],
        as: "peOption"
      }
    },
    {
      $addFields: {
        ce_token: { $getField: { field: "token", input: { $arrayElemAt: ["$ceOption", 0] } } },
        ce_tsym: { $getField: { field: "tsym", input: { $arrayElemAt: ["$ceOption", 0] } } },
        pe_token: { $getField: { field: "token", input: { $arrayElemAt: ["$peOption", 0] } } },
        pe_tsym: { $getField: { field: "tsym", input: { $arrayElemAt: ["$peOption", 0] } } }
      }
    },
    {
      $unset: ["ceOption", "peOption"]
    },
    {
      $lookup: {
        from: "OptionTick",
        let: { ft: "$ft", token_var: "$ce_token" },
        pipeline: [
          {
            $match: {
              $expr: {
                $and: [
                  { $eq: ["$ft", "$$ft"] },
                  { $eq: ["$token", "$$token_var"] }
                ]
              }
            }
          }
        ],
        as: "ceTick"
      }
    },
    {
      $lookup: {
        from: "OptionTick",
        let: { ft: "$ft", token_var: "$pe_token" },
        pipeline: [
          {
            $match: {
              $expr: {
                $and: [
                  { $eq: ["$ft", "$$ft"] },
                  { $eq: ["$token", "$$token_var"] }
                ]
              }
            }
          }
        ],
        as: "peTick"
      }
    },
    {
      $addFields: {
        ce_lp: { $getField: { field: "lp", input: { $arrayElemAt: ["$ceTick", 0] } } },
        pe_lp: { $getField: { field: "lp", input: { $arrayElemAt: ["$peTick", 0] } } }
      }
    },
    {
      $addFields: {
        sum_lp: { $round: [{ $add: ["$ce_lp", "$pe_lp"] }, 2] },
        diff: { $subtract: ["$pe_strike", "$ce_strike"] }
      }
    },
    {
      $addFields: {
        risk_prec: { 
          $round: [
            { 
              $subtract: [
                100, 
                { 
                  $multiply: [
                    { 
                      $cond: [
                        { $eq: ["$sum_lp", 0] }, 
                        0, 
                        { $divide: ["$diff", "$sum_lp"] }
                      ] 
                    }, 
                    100
                  ] 
                }
              ] 
            }, 
            2
          ] 
        }
      }
    },
    {
      $unset: ["ceTick", "peTick", "levels"]
    },
    {
      $project: {
        level: 1,
        ft: 1,
        e: 1,
        rt: 1,
        lotsize: 1,
        strkstep: 1,
        ibase: "$ce_strike",
        itop: "$pe_strike",
        ilp: "$lp",
        itoken: "$token",
        its: "$ts",
        ce_token: 1,
        pe_token: 1,
        ce_tsym: 1,
        pe_tsym: 1,
        ce_lp: 1,
        pe_lp: 1,
        sum_lp: 1,
        risk_prec: 1
      }
    }
  ]
);

print('View v_option_pair_base created successfully.'); 
